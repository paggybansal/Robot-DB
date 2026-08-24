*** Settings ***
Documentation     Shared configuration, libraries and setup for every suite.

Library           ../libraries/CaqhDatabase.py
Library           ../libraries/CaqhDefects.py
Library           ../libraries/CaqhAws.py
Library           Collections
Library           String
Variables         ../libraries/variables.py


*** Keywords ***
Prepare Database Suite
    [Documentation]    Suite Setup for suites that only need the database.
    ...                Skips the whole suite cleanly when there is no connection.
    ${available}=    Database Is Available
    Skip If    not ${available}
    ...    msg=No database. Set DB_HOST / DB_NAME / DB_USER in .env, or as GitHub Variables in CI.
    Log Defect Register
    Log    Connected to ${DB_NAME} on ${DB_HOST}    console=${True}

Prepare AWS Suite
    [Documentation]    Suite Setup for suites that need AWS.
    ${available}=    AWS Is Available
    Skip If    not ${available}
    ...    msg=No AWS credentials. Locally run 'aws sso login'. In CI check the OIDC role.
    AWS Should Be Available

Prepare Full Suite
    [Documentation]    Suite Setup for suites needing both.
    Prepare Database Suite
    Prepare AWS Suite

Rows Should Be Empty
    [Documentation]    Plain assertion for tests that are not tied to a known defect.
    [Arguments]    ${rows}    ${message}
    ${count}=    Row Count    ${rows}
    ${detail}=    Format Rows    ${rows}
    Should Be Equal As Integers    ${count}    0
    ...    msg=${message}\n\n${detail}
    ...    values=${False}

Report Count
    [Documentation]    Writes an informational count into the log and console.
    [Arguments]    ${rows}    ${label}
    ${count}=    Row Count    ${rows}
    Log    ${label}: ${count}    console=${True}
    RETURN    ${count}