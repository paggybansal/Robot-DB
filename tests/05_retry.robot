*** Settings ***
Documentation     STAGE 8-9 - retry and fallout.

Resource          ../resources/common.robot
Suite Setup       Set Up Retry Suite
Force Tags        stage5    retry


*** Variables ***
@{RETRY_ITEMS}    @{EMPTY}


*** Keywords ***
Set Up Retry Suite
    Prepare AWS Suite
    Skip If    '${RETRY_TABLE}' == ''
    ...    msg=RETRY_TABLE not set. Add it to .env or as a GitHub Variable.
    ${items}=    Scan Dynamo Table    ${RETRY_TABLE}
    Set Suite Variable    @{RETRY_ITEMS}    @{items}
    Log    ${RETRY_TABLE}: ${{ len($RETRY_ITEMS) }} item(s)    console=${True}


*** Test Cases ***
Retry Attempts Are Capped
    [Documentation]    DEF-034 (P1). With no cap, a permanently failing record
    ...                retries forever and hides real failures in the noise.
    [Tags]    defect:DEF-034    P1
    ${over}=     Items Exceeding Attempt Limit    ${RETRY_ITEMS}    ${MAX_RETRY_ATTEMPTS}
    ${count}=    Row Count    ${over}
    ${detail}=   Format Rows    ${over}
    Check Defect    DEF-034    ${over}
    ...    finding=${count} item(s) have retried more than ${MAX_RETRY_ATTEMPTS} times.\n${detail}
    ...    why=Without a cap a permanently failing record retries indefinitely, consuming capacity and drowning genuine failures.

Retry Items Carry An Error Reason
    [Documentation]    Without a reason nobody can tell a transient timeout from a
    ...                permanent validation failure, so triage is guesswork.
    Skip If    ${{ len($RETRY_ITEMS) }} == 0    msg=Retry table is empty
    ${missing}=    Items Missing Any Attribute    ${RETRY_ITEMS}
    ...    error    error_message    errorMessage    reason    failure_reason
    Rows Should Be Empty    ${missing}
    ...    Retry item(s) carry no error reason.

Retry Items Have A Timestamp Or TTL
    [Documentation]    Items with no age can never be identified as abandoned, so
    ...                the table grows without bound.
    Skip If    ${{ len($RETRY_ITEMS) }} == 0    msg=Retry table is empty
    ${missing}=    Items Missing Any Attribute    ${RETRY_ITEMS}
    ...    ttl    expires_at    expiry    created_at    createdAt    timestamp
    Rows Should Be Empty    ${missing}
    ...    Retry item(s) have no timestamp or TTL.

Retry Job Has Run
    [Documentation]    If records queue for retry but the job never runs, they are
    ...                stuck indefinitely.
    Skip If    '${GLUE_RETRY_JOB}' == ''    msg=GLUE_RETRY_JOB not set
    ${run}=    Get Last Glue Run    ${GLUE_RETRY_JOB}
    Should Not Be Empty    ${run}
    ...    msg=No runs found for ${GLUE_RETRY_JOB}.
    ...    values=${False}
    Log    Last retry run: ${run}[JobRunState] at ${run.get('StartedOn')}    console=${True}

Fallout Table Is Reachable
    Skip If    '${FALLOUT_TABLE}' == ''    msg=FALLOUT_TABLE not set
    ${items}=    Scan Dynamo Table    ${FALLOUT_TABLE}    limit=50
    Report Count    ${items}    Fallout items sampled