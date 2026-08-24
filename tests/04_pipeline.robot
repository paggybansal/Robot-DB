*** Settings ***
Documentation     STAGE 5-7 - transmission, audit and bookmark.
...               Observes the most recent real Glue run. Changes nothing.

Resource          ../resources/common.robot
Suite Setup       Set Up Pipeline Suite
Force Tags        stage4    pipeline


*** Variables ***
${RUN}            ${EMPTY}
${RUN_LOG}        ${EMPTY}


*** Keywords ***
Set Up Pipeline Suite
    Prepare AWS Suite
    Skip If    '${GLUE_STATUS_JOB}' == ''
    ...    msg=GLUE_STATUS_JOB not set. Add it to .env or as a GitHub Variable.
    ${run}=    Get Last Glue Run    ${GLUE_STATUS_JOB}
    Skip If    not ${run}    msg=No runs found for ${GLUE_STATUS_JOB}
    Set Suite Variable    ${RUN}    ${run}
    ${log}=    Get Glue Run Log    ${run}[Id]
    Set Suite Variable    ${RUN_LOG}    ${log}
    Log    Observing run ${run}[Id] (${run}[JobRunState])    console=${True}


*** Test Cases ***
Last Run Succeeded
    ${state}=    Set Variable    ${RUN}[JobRunState]
    ${error}=    Get From Dictionary    ${RUN}    ErrorMessage    default=(none reported)
    Should Be Equal    ${state}    SUCCEEDED
    ...    msg=Last run ended ${state}. Error: ${error}
    ...    values=${False}

Job Has Retries Configured
    [Documentation]    Zero retries means one transient failure loses the whole run.
    ${job}=       Get Glue Job    ${GLUE_STATUS_JOB}
    ${retries}=   Get From Dictionary    ${job}    MaxRetries    default=0
    ${timeout}=   Get From Dictionary    ${job}    Timeout       default=0
    Log    MaxRetries=${retries}  Timeout=${timeout} minutes    console=${True}
    Should Be True    ${retries} >= 1
    ...    msg=MaxRetries is ${retries}. A transient database or API failure fails the entire run. Combined with the bookmark advancing regardless, records can be skipped permanently with no alert.

No PHI In The Run Log
    [Documentation]    LOG-01 (P0). Names, NPIs, birth dates and full XML payloads
    ...                must not reach CloudWatch.
    [Tags]    defect:LOG-01    P0    security
    ${found}=    Find PHI In Text    ${RUN_LOG}
    ${detail}=   Format Rows    ${found}
    Check Defect    LOG-01    ${found}
    ...    finding=PHI found in CloudWatch.\n${detail}
    ...    why=Log retention makes this a persistent, searchable copy of protected health information outside the application boundary.

Run Reports A Processed Count
    ${count}=    Extract From Text    ${RUN_LOG}    total[_ ]count["'\\s:=]+(\\d+)
    Should Not Be Empty    ${count}
    ...    msg=No processed count in the run log. Without one there is no way to reconcile what was sent against what was eligible.
    Log    Run reported total_count = ${count}    console=${True}

Bookmark Is Readable
    Skip If    '${S3_BUCKET}' == '' or '${BOOKMARK_KEY}' == ''
    ...    msg=S3_BUCKET / BOOKMARK_KEY not set
    ${value}=    Read Bookmark
    Should Not Be Equal    ${value}    ${None}
    ...    msg=Could not read s3://${S3_BUCKET}/${BOOKMARK_KEY}. If the bookmark is unreadable the next run's selection window is undefined.
    ...    values=${False}
    Log    Bookmark = ${value}    console=${True}

Bookmark Did Not Advance Past Failures
    [Documentation]    DEF-033 (P1). If the bookmark moves past a failed record,
    ...                that record is never selected again.
    [Tags]    defect:DEF-033    P1
    ${failures}=    Count Matches In Text    ${RUN_LOG}    \\b(error|failed|exception)\\b
    Skip If    ${failures} == 0    msg=No failures in the last run - nothing to check
    ${value}=       Read Bookmark
    ${evidence}=    Create List
    IF    ${value} is not None
        ${flag}=    Get From Dictionary    ${value}    has_failures    default=${None}
        IF    ${flag} is None
            ${evidence}=    Create List    ${value}
        END
    END
    Check Defect    DEF-033    ${evidence}
    ...    finding=${failures} failure indication(s) in the run, but the bookmark carries no record of them: ${value}
    ...    why=If the bookmark advances past a failed record, that record is never re-selected and is lost silently.