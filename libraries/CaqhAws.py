"""Robot keywords for AWS: Glue, DynamoDB, S3, CloudWatch."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from robot.api import logger
from robot.api.deco import keyword, library
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from libraries.config import get_settings

_RETRY = retry(
    retry=retry_if_exception_type((ClientError, BotoCoreError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)


@library(scope="GLOBAL", version="1.0", auto_keywords=False)
class CaqhAws:
    """Observes the deployed pipeline. Read-only."""

    @staticmethod
    @lru_cache(maxsize=1)
    def _session() -> boto3.Session:
        settings = get_settings()
        if settings.aws_profile:
            return boto3.Session(
                profile_name=settings.aws_profile, region_name=settings.aws_region
            )
        return boto3.Session(region_name=settings.aws_region)  # CI: OIDC role

    @lru_cache(maxsize=None)  # noqa: B019
    def _client(self, service: str):
        return self._session().client(
            service,
            config=Config(
                retries={"max_attempts": 5, "mode": "adaptive"},
                connect_timeout=10, read_timeout=60,
            ),
        )

    # -------------------------------------------------------------- keywords

    @keyword("AWS Is Available")
    def aws_is_available(self) -> bool:
        """Returns True or False. Use with Skip If, never raises."""
        try:
            self._client("sts").get_caller_identity()
            return True
        except Exception:
            return False

    @keyword("AWS Should Be Available")
    def aws_should_be_available(self) -> None:
        try:
            who = self._client("sts").get_caller_identity()
        except Exception as exc:
            raise AssertionError(
                f"No AWS credentials.\n"
                f"Locally:  aws sso login --profile {get_settings().aws_profile}\n"
                f"In CI:    check the OIDC role in the workflow\n"
                f"{str(exc).splitlines()[0][:160]}"
            ) from None
        logger.info(f"AWS account {who['Account']}")

    @keyword("Get Glue Job")
    @_RETRY
    def get_glue_job(self, name: str) -> dict[str, Any]:
        return self._client("glue").get_job(JobName=name)["Job"]

    @keyword("Get Last Glue Run")
    @_RETRY
    def get_last_glue_run(self, job_name: str) -> dict[str, Any]:
        """Most recent run of a Glue job. Returns an empty dict if there are none."""
        runs = self._client("glue").get_job_runs(JobName=job_name, MaxResults=1)["JobRuns"]
        if not runs:
            return {}
        run = runs[0]
        logger.info(
            f"{job_name}: run {run['Id']} state={run['JobRunState']} "
            f"started={run.get('StartedOn')}"
        )
        return run

    @keyword("Get Glue Run Log")
    def get_glue_run_log(self, run_id: str) -> str:
        """Combined output and error log text for one Glue run."""
        logs, chunks = self._client("logs"), []
        for group in ("/aws-glue/jobs/output", "/aws-glue/jobs/error"):
            try:
                streams = logs.describe_log_streams(
                    logGroupName=group, logStreamNamePrefix=run_id, limit=5
                )["logStreams"]
            except ClientError:
                continue
            for stream in streams:
                try:
                    events = logs.get_log_events(
                        logGroupName=group, logStreamName=stream["logStreamName"],
                        startFromHead=True, limit=10000,
                    )["events"]
                    chunks.extend(event["message"] for event in events)
                except ClientError:
                    continue
        text = "\n".join(chunks)
        logger.info(f"retrieved {len(text):,} characters of log")
        return text

    @keyword("Find PHI In Text")
    def find_phi_in_text(self, text: str) -> list[dict[str, str]]:
        """Returns a row per kind of PHI found. Empty list means clean."""
        patterns = {
            "full CAQH profile XML": r"<\s*\w*Practitioner\w*Profile",
            "date of birth": r"\bbirth_?date['\"]?\s*[:=]\s*['\"]?\d{4}-\d{2}-\d{2}",
            "NPI": r"\bnpi['\"]?\s*[:=]\s*['\"]?\d{10}",
            "practitioner name": r"\b(first_name|last_name)['\"]?\s*[:=]\s*['\"][A-Za-z]",
            "CAQH ID": r"\bcaqh_?id['\"]?\s*[:=]\s*['\"]?\d{5,}",
        }
        found = []
        for label, pattern in patterns.items():
            hits = re.findall(pattern, text, re.I)
            if hits:
                found.append({"kind": label, "occurrences": str(len(hits))})
        return found

    @keyword("Count Matches In Text")
    def count_matches_in_text(self, text: str, pattern: str) -> int:
        return len(re.findall(pattern, text, re.I))

    @keyword("Extract From Text")
    def extract_from_text(self, text: str, pattern: str, default: str = "") -> str:
        match = re.search(pattern, text, re.I)
        return match.group(1) if match and match.groups() else default

    @keyword("Scan Dynamo Table")
    @_RETRY
    def scan_dynamo_table(self, table: str, limit: int = 500) -> list[dict[str, Any]]:
        items = self._client("dynamodb").scan(TableName=table, Limit=int(limit)).get("Items", [])
        logger.info(f"{table}: {len(items)} item(s)")
        return items

    @keyword("Items Exceeding Attempt Limit")
    def items_exceeding_attempt_limit(
        self, items: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        """Retry items whose attempt count is above ``limit``."""
        names = ("attempt", "attempts", "retry_count", "retryCount", "tries")
        over = []
        for item in items:
            for name in names:
                if name in item:
                    raw = item[name].get("N") or item[name].get("S") or ""
                    try:
                        value = int(float(raw))
                    except (TypeError, ValueError):
                        continue
                    if value > int(limit):
                        first_key = next(iter(item))
                        ident = item[first_key].get("S") or item[first_key].get("N") or "?"
                        over.append({"item": ident, "attempts": value})
                    break
        return over

    @keyword("Items Missing Any Attribute")
    def items_missing_any_attribute(
        self, items: list[dict[str, Any]], *attributes: str
    ) -> list[dict[str, Any]]:
        """Items that have none of the named attributes."""
        wanted = set(attributes)
        missing = []
        for item in items:
            if not (wanted & set(item)):
                first_key = next(iter(item))
                ident = item[first_key].get("S") or item[first_key].get("N") or "?"
                missing.append({"item": ident, "keys_present": ",".join(sorted(item))})
        return missing

    @keyword("Read S3 Json")
    def read_s3_json(self, bucket: str, key: str) -> Any:
        try:
            body = self._client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
            return json.loads(body)
        except Exception as exc:
            logger.warn(f"could not read s3://{bucket}/{key}: {str(exc)[:120]}")
            return None

    @keyword("Read Bookmark")
    def read_bookmark(self) -> Any:
        settings = get_settings()
        if not (settings.s3_bucket and settings.bookmark_key):
            return None
        return self.read_s3_json(settings.s3_bucket, settings.bookmark_key)