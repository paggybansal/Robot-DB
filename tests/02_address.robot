*** Settings ***
Documentation     STAGE 3 - which address is sent to CAQH.

Resource          ../resources/common.robot
Suite Setup       Prepare Database Suite
Force Tags        stage2    address


*** Test Cases ***
Practitioners With A Service Address Keep It
    [Documentation]    DEF-004 (P0). The pipeline ranks all address types first,
    ...                then filters to Service - so it can lose the only row.
    [Tags]    defect:DEF-004    P0
    ${rows}=     Run Reference Query    address_lost_by_ranking
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}
    Check Defect    DEF-004    ${rows}
    ...    finding=${count} practitioner(s) have a valid ${SERVICE_ADDRESS_TYPE} address but will send no address at all.\n${detail}
    ...    why=Addresses are ranked newest-first across ALL types and only then filtered to ${SERVICE_ADDRESS_TYPE}. When the newest is Mail or Billing, the filter removes the only ranked row and the practitioner falls out silently.

Each Practitioner Resolves To Exactly One Address
    [Documentation]    CAQH expects one practice location per submission.
    ${rows}=    Run Reference Query    correct_address
    ${ids}=     Column Values    ${rows}    PractitionerID
    ${unique}=    Remove Duplicates    ${ids}
    ${total}=     Get Length    ${ids}
    ${distinct}=  Get Length    ${unique}
    Should Be Equal As Integers    ${total}    ${distinct}
    ...    msg=${total} address rows for ${distinct} practitioners - at least one resolves to more than one address.
    ...    values=${False}

Address Choice Is Deterministic
    [Documentation]    DATA-02 (P2). Ties on DateFrom mean the address sent can
    ...                change between runs with no data change.
    [Tags]    defect:DATA-02    P2
    ${rows}=     Run Reference Query    address_ties
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}
    Check Defect    DATA-02    ${rows}
    ...    finding=${count} practitioner(s) have two or more ${SERVICE_ADDRESS_TYPE} addresses sharing a DateFrom.\n${detail}
    ...    why=ROW_NUMBER orders by DateFrom alone. With a tie the winner is whatever the engine returns first, so the address sent to CAQH can change between runs.

Practitioners Without A Service Address Are Counted
    [Documentation]    Informational. Legitimate fallout, kept separate from DEF-004
    ...                so the two are not conflated in reporting.
    ${rows}=     Run Reference Query    no_service_address
    ${count}=    Report Count    ${rows}    Eligible with no ${SERVICE_ADDRESS_TYPE} address
    Log    These are legitimate fallout, not a code defect. Report them separately from DEF-004.