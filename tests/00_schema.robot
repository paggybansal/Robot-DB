*** Settings ***
Documentation     STAGE 0 - does this database match what the suite expects?
...
...               Run this first. Every failure names a table, column or setting
...               to correct. Once this suite is green, the rest is meaningful.

Resource          ../resources/common.robot
Suite Setup       Prepare Database Suite
Force Tags        stage0    schema


*** Test Cases ***
Required Tables Exist
    [Documentation]    Each row is one table the reference queries rely on.
    [Template]    Table Should Exist
    Practitioners
    entityAssignments
    entities
    StatusTypes
    CommitteeActions
    Locations
    AddressTypes
    PractitionerProfessionalIDs
    ProfessionalIDTypes
    PractitionerTypes

Required Columns Exist
    [Documentation]    Each row is one column the reference queries rely on.
    [Template]    Column Should Exist
    Practitioners                  PractitionerID
    Practitioners                  NPI
    Practitioners                  FirstName
    Practitioners                  LastName
    Practitioners                  BirthDate
    Practitioners                  GenderID
    Practitioners                  PractitionerTypeID
    Practitioners                  Archived
    entityAssignments              ParentRecID
    entityAssignments              EntityID
    entityAssignments              ChangedOn
    entities                       EntityName
    StatusTypes                    StatusTypeName
    CommitteeActions               CommitteeActionName
    Locations                      PractitionerID
    Locations                      AddressTypeID
    Locations                      Address1
    Locations                      DateFrom
    AddressTypes                   AddressTypeName
    PractitionerProfessionalIDs    IDNumber
    ProfessionalIDTypes            ProfessionalIDTypeName
    PractitionerTypes              Archived

Configured Business Values Exist In The Data
    [Documentation]    Confirms the values in .env really appear in this database.
    [Template]    Reference Value Should Exist
    entities               EntityName              ${CLIENT_ENTITY}          CLIENT_ENTITY
    StatusTypes            StatusTypeName          ${TRIGGER_STATUS}         TRIGGER_STATUS
    AddressTypes           AddressTypeName         ${SERVICE_ADDRESS_TYPE}   SERVICE_ADDRESS_TYPE
    ProfessionalIDTypes    ProfessionalIDTypeName  ${CAQH_ID_TYPE}           CAQH_ID_TYPE

Credentialing Actions Exist In The Data
    [Documentation]    Every value in CRED_ACTIONS must be a real committee action.
    FOR    ${action}    IN    @{CRED_ACTIONS}
        Reference Value Should Exist
        ...    CommitteeActions    CommitteeActionName    ${action}    CRED_ACTIONS
    END

Eligible Population Is Not Empty
    [Documentation]    If this is zero, every later test proves nothing.
    ...                Either this environment has no data in that state, or one of
    ...                CLIENT_ENTITY / TRIGGER_STATUS / CRED_ACTIONS is wrong.
    ${rows}=    Run Reference Query    eligible_practitioners
    ${count}=    Report Count    ${rows}    Eligible practitioners
    Should Be True    ${count} > 0
    ...    msg=No eligible practitioners found. Run 'python tools/discover.py' section 9.

Selection Is Repeatable
    [Documentation]    The same query twice must return the same population.
    ${first}=     Run Reference Query    eligible_practitioners
    ${second}=    Run Reference Query    eligible_practitioners
    ${a}=    Column Values    ${first}     PractitionerID
    ${b}=    Column Values    ${second}    PractitionerID
    Lists Should Be Equal    ${a}    ${b}
    ...    msg=Two identical runs returned different populations. Either data is changing under us, or the query is non-deterministic.
    ...    ignore_order=${True}