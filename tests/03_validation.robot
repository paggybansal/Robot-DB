*** Settings ***
Documentation     STAGE 4 - duplicates and missing required fields.

Resource          ../resources/common.robot
Suite Setup       Prepare Database Suite
Force Tags        stage3    validation


*** Test Cases ***
Blank CAQH ID Row Does Not Cause A Duplicate Rejection
    [Documentation]    DEF-021 (P0). A blank ID row alongside a real one is counted
    ...                as a duplicate, so a valid practitioner is rejected.
    [Tags]    defect:DEF-021    P0
    ${rows}=     Run Reference Query    blank_caqh_id_pairs
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}
    Check Defect    DEF-021    ${rows}
    ...    finding=${count} practitioner(s) have one real ${CAQH_ID_TYPE} plus a blank row.\n${detail}
    ...    why=The blank is counted as a second identifier, so a practitioner with exactly one usable CAQH ID is rejected as a duplicate and never sent.

Genuinely Conflicting CAQH IDs Are Counted
    [Documentation]    Informational. These SHOULD be rejected - confirms that
    ...                fixing DEF-021 will not disable real duplicate detection.
    ${rows}=     Run Reference Query    conflicting_caqh_ids
    ${count}=    Report Count    ${rows}    Practitioners with two different non-blank CAQH IDs
    Log    These need a DATA fix, not a code fix. Rejection is correct here.

Eligible Practitioners Have An NPI
    [Documentation]    DATA-01 (P1). NPI is mandatory at CAQH, so each of these is
    ...                a guaranteed rejection.
    [Tags]    defect:DATA-01    P1
    ${rows}=     Run Reference Query    missing_npi
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}    limit=10
    Check Defect    DATA-01    ${rows}
    ...    finding=${count} eligible practitioner(s) have no NPI.\n${detail}
    ...    why=Each is a guaranteed CAQH rejection that could be caught before transmission instead of appearing as an opaque API error.

NPI Values Are Ten Digits
    [Documentation]    A value like 9999000001.0 also shows NPI is being handled
    ...                as a number rather than text.
    ${rows}=    Run Reference Query    malformed_npi
    Rows Should Be Empty    ${rows}
    ...    Practitioner(s) have an NPI that is not exactly 10 digits. CAQH rejects malformed NPIs.

Birth Dates Are Plausible
    ${rows}=    Run Reference Query    bad_birth_date
    Rows Should Be Empty    ${rows}
    ...    Eligible practitioner(s) have a missing or impossible birth date.

Gender Values Are All Mapped
    [Documentation]    DEF-032 (P1). Unmapped values pass through to CAQH as-is.
    [Tags]    defect:DEF-032    P1
    ${rows}=     Run Reference Query    unmapped_gender
    ${detail}=   Format Rows    ${rows}
    Check Defect    DEF-032    ${rows}
    ...    finding=Unmapped gender value(s) in the eligible population.\n${detail}
    ...    why=An unmapped value is forwarded to CAQH unchanged. Better to fail here with a clear reason than to be rejected by CAQH with an opaque one.

Provider Types Resolve For Every Eligible Practitioner
    [Documentation]    DEF-036 (P2). The main query treats NULL Archived as active;
    ...                the provider type lookup requires Archived = 'N'.
    [Tags]    defect:DEF-036    P2
    ${nulls}=    Run Reference Query    null_archived_provider_types
    ${rows}=     Run Reference Query    unresolvable_provider_type
    ${nullcount}=    Row Count    ${nulls}
    ${count}=        Row Count    ${rows}
    ${detail}=       Format Rows    ${rows}
    Check Defect    DEF-036    ${rows}
    ...    finding=${count} eligible practitioner(s) have a provider type the lookup cannot resolve. ${nullcount} provider type(s) have Archived = NULL.\n${detail}
    ...    why=The two queries disagree about what 'active' means, so a record is selected and then cannot be completed.