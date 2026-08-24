*** Settings ***
Documentation     STAGE 1-2 - who gets picked up, and with what detail.

Resource          ../resources/common.robot
Suite Setup       Prepare Database Suite
Force Tags        stage1    selection


*** Test Cases ***
No Practitioner Is Selected More Than Once
    [Documentation]    DEF-008 (P0). A practitioner with several qualifying
    ...                assignment rows is submitted to CAQH once per row.
    [Tags]    defect:DEF-008    P0
    ${rows}=     Run Reference Query    fan_out
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}
    Check Defect    DEF-008    ${rows}
    ...    finding=${count} practitioner(s) have multiple qualifying rows.\n${detail}
    ...    why=Without DISTINCT the selection query returns one row per join match, so the same practitioner is submitted to CAQH repeatedly in one run and the reported total is wrong.

Reported Count Equals Practitioners Processed
    [Documentation]    DEF-008 (P0). count(*) counts joined rows, not practitioners.
    [Tags]    defect:DEF-008    P0
    ${rows}=       Run Reference Query    eligible_row_count
    ${joined}=     Set Variable    ${rows}[0][joined_rows]
    ${distinct}=   Set Variable    ${rows}[0][distinct_practitioners]
    ${overstated}=    Evaluate    ${joined} - ${distinct}
    ${mismatch}=      Create List    @{EMPTY}
    IF    ${overstated} > 0
        ${mismatch}=    Create List    ${rows}[0]
    END
    Check Defect    DEF-008    ${mismatch}
    ...    finding=count(*) reports ${joined} but only ${distinct} practitioners exist - overstated by ${overstated}.
    ...    why=Every downstream report, reconciliation and audit total is wrong by this amount.

Credentialing Type Is Unambiguous
    [Documentation]    DEF-009 (P0). When qualifying rows disagree about the
    ...                credentialing type, the detail query picks arbitrarily.
    [Tags]    defect:DEF-009    P0
    ${rows}=     Run Reference Query    ambiguous_cred_type
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}    limit=5
    Check Defect    DEF-009    ${rows}
    ...    finding=${count} practitioner(s) have qualifying rows with different credentialing types.\n${detail}
    ...    why=The detail query has no ChangedOn filter, so which type reaches CAQH depends on row order rather than which row triggered selection.

Assignment Rows All Belong To Practitioners
    [Documentation]    DEF-005 (P0, awaiting answer). ParentRecID is joined with
    ...                no parent-type discriminator.
    [Tags]    defect:DEF-005    P0
    ${rows}=     Run Reference Query    orphan_assignments
    ${count}=    Row Count    ${rows}
    ${detail}=   Format Rows    ${rows}    limit=10
    Check Defect    DEF-005    ${rows}
    ...    finding=${count} assignment row(s) have a ParentRecID that is not a practitioner.\n${detail}
    ...    why=The join is on ParentRecID alone. If those IDs collide with practitioner IDs, an assignment about a different record type is attached to a practitioner.