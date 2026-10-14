"""Seed synthetic tickets into MongoDB Atlas as Knowledge Sources and Investigations."""
import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import openpyxl

from config import settings
from storage import MongoStore
from ai import AIService
from ingestion import chunks, now

CSV_TEXT = """ticket_id,dataset_role,scenario_group,ticket_type,priority,customer,platform,release,module,component,customized,visibility,title,problem_statement,error_message,investigation_notes,resolution,resolution_quality,root_cause,status,created,closed,resolution_hours,linked_ticket_ids,ground_truth
SYN-H001,history,G1 Approval flow,Incident,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,MM,MM-PUR-GF-REL,False,shared_generalized,PO saved without release strategy for new plant 3200,"Purchase orders for newly created plant 3200 are saved with no release strategy, so no approver is assigned and POs go straight to the vendor.",No release strategy determined (no message; release indicator blank),Compared with plant 1000 where approval works. Release strategy classification shows plant values only for existing plants.,Added plant 3200 to the characteristic value list for plant and re-saved the release strategy classification. Re-determined release strategy on open POs. Tested with a new PO.,Confirmed root cause,New plant missing from release strategy characteristic values,Closed,2025-01-14,2025-01-15,6.5,,
SYN-H002,history,G1 Approval flow,Incident,High,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,MM,MM-PUR-REQ,False,shared_generalized,Purchase requisition approval not triggered for new document type,Requisitions created in Fiori with new document type ZNB are approved automatically. Managers expect an approval task.,No workflow task created; PR status 'Released' on save,Release strategy not used in this system. Approval runs through flexible workflow for purchase requisitions. No start condition covers ZNB.,"In the 'Manage Workflows for Purchase Requisitions' app, added a start condition for document type ZNB, assigned approver by responsibility rule, and activated the workflow version. Verified with test PR.",Confirmed root cause,Flexible workflow start condition did not cover new document type,Closed,2025-08-20,2025-08-21,5.0,,
SYN-H003,history,G1 Approval flow,Incident,Medium,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,MM,MM-PUR-PO,False,shared_generalized,PO approval request never reaches manager,Purchase order approval is created but the manager says nothing appears in the inbox.,"Workflow task exists, status 'Ready', no recipient visibility",Manager business user has no business role containing the inbox app. Responsibility for the approval step is not maintained for the purchasing group.,Assigned the business role containing My Inbox to the manager user and maintained the team responsibility for the purchasing group in the responsibility management app.,Confirmed root cause,Missing business role and missing approver responsibility,Closed,2025-05-09,2025-05-10,3.0,,
SYN-H004,history,G1 Approval flow,Incident,Medium,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,MM,MM-PUR-GF-REL,False,shared_generalized,Approver cannot see POs awaiting release,A new approver is assigned release code 04 but the PO list for release shows nothing.,No POs found in release transaction for this user,Release strategy is correct. User has no authorization for the release code in the authorization object for release.,Added the release code and group to the user's role through the role maintenance tool and regenerated the profile.,Confirmed root cause,Approver missing authorization for release code,Closed,2025-03-03,2025-03-04,2.0,,
SYN-H005,history,G2 Posting period not open,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,FI,FI-GL-GL-A,False,shared_generalized,Posting period not open for company code 1000,Finance cannot post a G/L journal for the current month.,Posting period 03 2025 is not open,Period control table showed account type S closed for period 03 under the posting period variant.,Opened period 03 for account types in the period control after written approval from the Finance Controller.,Confirmed root cause,Period closed in period control,Closed,2025-04-02,2025-04-03,1.0,,
SYN-H006,history,G2 Posting period not open,Incident,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,FI-GL-GL-A,False,shared_generalized,Posting period not open for new company code 2100 although period is open,Period is open in period control yet postings fail only for new company code 2100.,Posting period 04 2025 is not open,Company code 2100 was assigned to a posting period variant different from the one maintained during month-end opening.,"Reassigned company code 2100 to the shared posting period variant, confirmed with Finance, and re-tested posting.",Confirmed root cause,Company code assigned to wrong posting period variant,Closed,2025-05-06,2025-05-07,2.5,,
SYN-H007,history,G2 Posting period not open,Incident,Medium,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,FI,FI-AA,False,shared_generalized,Asset posting rejected: period not open although G/L period open,Asset acquisition posting is rejected. G/L postings in the same company code work.,Posting period not open for asset area,G/L period open. The fixed asset period for the depreciation area had been closed by the period-end team.,Asset accounting team reopened the asset period under an approved request; posting retried successfully.,Confirmed root cause,Asset accounting period closed separately from G/L period,Closed,2025-09-10,2025-09-11,4.0,,
SYN-H008,history,G2 Posting period not open,Incident,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,FI-GL-GL-A,True,customer_only,Posting period not open for document type ZR after day 5 though period open,Reversal postings with document type ZR are blocked after the 5th working day.,Posting period 06 2025 is not open,Period control and variant are correct. A custom BAdI implementation applies an additional cut-off for document type ZR using a Z configuration table.,Developer updated the Z exception table to allow ZR for approved controllers and documented the cut-off logic.,Confirmed root cause,Custom BAdI cut-off rule for document type ZR,Closed,2025-07-08,2025-07-10,8.0,,
SYN-H009,history,G3 MRP,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,PP,PP-MRP,False,shared_generalized,Overnight MRP run times out for plant 1000,Total planning run for plant 1000 does not finish before morning.,Job cancelled: runtime exceeded,Planning file contains about 400k entries because all materials flagged for planning.,"Switched to net change planning mode with a processing key, split runs by MRP controller, and cleaned unnecessary planning file entries.",Confirmed root cause,Total planning on a very large planning file,Closed,2025-02-12,2025-02-14,12.0,,
SYN-H010,history,G3 MRP,Incident,Medium,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,PP,PP-MRP,False,shared_generalized,Classic MRP run not recommended; planned orders not created,Planner uses the classic MRP transaction and no planned orders appear for MRP area 1000.,Transaction not recommended in S/4HANA; use MRP Live,MRP area planning needs the new MRP Live transaction. Classic run skipped the MRP area.,Switched to MD01N and scheduled recurring runs through the Fiori app for scheduling MRP runs.,Confirmed root cause,Using obsolete classic MRP transaction in S/4HANA,Closed,2025-10-01,2025-10-02,3.0,,
SYN-H011,history,G4 Billing account determination,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,SD,SD-BIL,False,shared_generalized,Billing blocked: error in account determination for new material group,Billing document cannot be released to accounting after a new material group was introduced.,Error in account determination: table T030 key 1000 ... ERL,No revenue account condition record for the new account assignment group of material in sales org 1000.,Added the condition record in revenue account determination (VKOA) for the new material account assignment group and reprocessed billing.,Confirmed root cause,Missing revenue account determination record,Closed,2025-02-25,2025-02-26,2.0,,
SYN-H012,history,G4 Billing account determination,Incident,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,SD,SD-BIL,False,shared_generalized,Billing account determination error although condition record exists,Same account determination error for company code 2100. Condition record exists.,Error in account determination: table T030 key 2100 ... ERL,Revenue G/L account exists in the chart of accounts but was never extended to company code 2100.,Extended G/L account to company code 2100 and reprocessed billing documents.,Confirmed root cause,G/L account not extended to company code,Closed,2025-04-17,2025-04-18,1.5,,
SYN-H013,history,G4 Billing account determination,Incident,High,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,SD,SD-BIL,False,shared_generalized,Billing error for migrated customers after Business Partner conversion,Billing fails for customers created through Business Partner after migration.,Error in account determination for customer account assignment group,Customer account assignment group is blank in the sales area data for migrated business partners.,Maintained the account assignment group in the customer sales area role through BP and rebuilt affected billing documents.,Confirmed root cause,Missing customer account assignment group after BP migration,Closed,2025-07-22,2025-07-23,4.0,,
SYN-H014,history,G4 Billing account determination,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,SD,SD-BIL,False,shared_generalized,Intermittent account determination error on billing,Billing document showed an account determination error. Error disappeared later.,Error in account determination: table T030,Consultant retried billing next morning and it worked. No configuration change was identified. Possibly related to an overnight transport.,Retried billing and released to accounting. Closed as resolved.,Workaround only,,Closed,2025-06-03,2025-06-04,0.5,,
SYN-H015,history,G5 Authorization / missing app,Incident,Medium,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,BC,BC-SEC,False,shared_generalized,No authorization to create purchase order,New buyer gets authorization error on PO creation.,You have no authorization for transaction ME21N (S_TCODE),Authorization trace shows transaction code missing from the role.,Added the transaction code to the buyer role through the role maintenance tool and generated the profile.,Confirmed root cause,Transaction code missing in role,Closed,2025-01-27,2025-01-28,1.0,,
SYN-H016,history,G5 Authorization / missing app,Incident,Medium,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,BC,BC-SEC-LP,False,shared_generalized,Fiori tile missing for AP clerk after role change,AP clerks do not see the 'Manage Supplier Invoices' tile after roles were updated.,Tile not visible; app not found in launchpad,Role contains the back-end authorizations but the business catalog was removed from the role during cleanup.,"Re-added the business catalog and space/page assignment to the role, regenerated, and invalidated launchpad client caches.",Confirmed root cause,Business catalog dropped from role,Closed,2025-09-02,2025-09-03,2.0,,
SYN-H017,history,G5 Authorization / missing app,Incident,Medium,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,BC,BC-SEC,False,shared_generalized,Tile missing for finance user in public cloud,Finance user cannot see the journal entry app.,App not visible on home page,"Business user exists but the relevant business role is not assigned, or restrictions are not set.",Assigned the business role through the business user maintenance app and set write restrictions for company code.,Confirmed root cause,Business role not assigned,Closed,2025-06-18,2025-06-19,1.0,,
SYN-H018,history,G5 Authorization / missing app,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,SD,SD-BIL,True,customer_only,Custom pricing report fails with custom authorization check,Pricing analysts cannot run report ZSD_PRICE_RPT.,No authorization for authorization object Z_PRCGRP,"Custom authorization object introduced by the report developer, not part of any standard role.",Added Z_PRCGRP to the analyst role and documented it in the custom solution inventory.,Confirmed root cause,Custom authorization object not in role,Closed,2025-03-25,2025-03-26,3.0,,
SYN-H019,history,G6 IDoc processing,Incident,Medium,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,SD,SD-EDI,False,shared_generalized,Inbound sales order IDocs fail for new customer,Orders from new EDI partner 'RETAILX' are not created.,IDoc status 56: partner profile not available,Inbound partner profile not maintained for sender RETAILX.,"Created the inbound partner profile with message type ORDERS and process code, then reprocessed IDocs.",Confirmed root cause,Partner profile missing,Closed,2025-02-05,2025-02-06,2.0,,
SYN-H020,history,G6 IDoc processing,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,FI,FI-AP,False,shared_generalized,Inbound invoice IDocs status 51 – posting period not open,Supplier invoice IDocs are stuck in error after month end.,IDoc status 51: Posting period 03 2025 is not open,Error details point to FI period control. Period closed after cut-off but invoices still arrive.,"Finance opened the period for AP, then IDocs were reprocessed in bulk. Agreed cut-off communication with the business.",Confirmed root cause,Period closed while late invoices still arriving,Closed,2025-04-04,2025-04-05,3.0,SYN-H005,
SYN-H021,history,G6 IDoc processing,Incident,Medium,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,MM,MM-IDOC,True,customer_only,Material master IDoc status 51 after custom field added,Inbound material IDocs fail after a new mandatory custom field was added.,IDoc status 51: Field ZZSEASON requires an entry,Mandatory custom field introduced by enhancement. Inbound segment mapping does not fill it.,Developer updated inbound mapping and default logic; reprocessed IDocs.,Confirmed root cause,Custom mandatory field not mapped in inbound IDoc,Closed,2025-10-14,2025-10-15,6.0,,
SYN-H022,history,G6 IDoc processing,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,BC,BC-SRV-ALE,False,shared_generalized,IDocs stuck in status 64 (ready to be passed to application),Inbound IDocs are not processed automatically.,IDoc status 64,Manually reprocessed through the IDoc processing transaction and they posted. Unsure why the job did not run.,Reprocessed IDocs manually. Closed after confirming postings.,Workaround only,,Closed,2025-05-28,2025-05-29,1.0,,
SYN-H023,history,G7 Custom code dumps,Incident,Medium,Cendana Retail Sdn Bhd,ECC,ECC 6.0 EHP8,MM,MM-IM,True,customer_only,Custom stock report dumps for large plant selection,Report ZMM_STOCK_RPT crashes with memory dump on selection of all plants.,ABAP runtime error TSV_TNEW_PAGE_ALLOC_FAILED,Report reads all stock rows into an internal table without package processing.,Developer introduced package-size processing and made plant selection mandatory.,Confirmed root cause,Unbounded SELECT into internal table,Closed,2024-11-12,2024-11-14,8.0,,
SYN-H024,history,G7 Custom code dumps,Incident,High,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,MM,MM-IM,True,customer_only,Custom goods receipt report dumps after S/4HANA conversion,Report ZMM_GR_RPT fails after conversion.,ABAP runtime error: field MSEG-ZZCOLOR unknown,Report reads the old material document table and relies on custom append fields not present in the converted data model.,Developer re-pointed the report to the new material document view and moved the ZZ fields to the supported extension. Retested.,Confirmed root cause,Custom code relies on obsolete table structure,Closed,2025-06-11,2025-06-14,16.0,,
SYN-H025,history,G7 Custom code dumps,Incident,Medium,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,FI,FI-GL,True,customer_only,Custom G/L line item report times out,Report ZFI_LINEITEM_RPT times out in dialog mode.,ABAP runtime error TIME_OUT,"Report reads the universal journal table without restricting ledger, company code and fiscal year.",Added selection fields to WHERE clause and scheduled in background for large ranges.,Confirmed root cause,Non-selective read on journal table,Closed,2025-11-04,2025-11-05,6.0,,
SYN-H026,history,G7 Custom code dumps,Incident,Medium,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,BC,BC-DWB,True,customer_only,Custom interface dumps after transport import,Interface program ZIF_ORDER_OUT dumps in QA after transport.,ABAP runtime error CALL_FUNCTION_NOT_FOUND,Function module was in a separate transport that was not imported.,Imported the missing transport and added both objects to one release request.,Confirmed root cause,Missing dependent transport,Closed,2025-08-12,2025-08-13,2.0,,
SYN-H027,history,G8 Recurring batch job cancellation,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Job ZFI_DAILY_UPLOAD cancelled overnight (1),Nightly bank file upload job was cancelled and reconciliation did not run.,Job cancelled; lock error on table ZFI_UPL,Restarted the job in the morning and it completed. No investigation into why it was cancelled.,Restarted job manually. Closed.,Workaround only,,Closed,2025-02-03,2025-02-04,0.5,,
SYN-H028,history,G8 Recurring batch job cancellation,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Job ZFI_DAILY_UPLOAD cancelled overnight (2),Nightly bank file upload job was cancelled and reconciliation did not run.,Job cancelled; lock error on table ZFI_UPL,Restarted the job in the morning and it completed. No investigation into why it was cancelled.,Restarted job manually. Closed.,Workaround only,,Closed,2025-02-17,2025-02-18,0.5,,
SYN-H029,history,G8 Recurring batch job cancellation,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Job ZFI_DAILY_UPLOAD cancelled overnight (3),Nightly bank file upload job was cancelled and reconciliation did not run.,Job cancelled; lock error on table ZFI_UPL,Restarted the job in the morning and it completed. No investigation into why it was cancelled.,Restarted job manually. Closed.,Workaround only,,Closed,2025-03-04,2025-03-05,0.5,,
SYN-H030,history,G8 Recurring batch job cancellation,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Job ZFI_DAILY_UPLOAD cancelled overnight (4),Nightly bank file upload job was cancelled and reconciliation did not run.,Job cancelled; lock error on table ZFI_UPL,Restarted the job in the morning and it completed. No investigation into why it was cancelled.,Restarted job manually. Closed.,Workaround only,,Closed,2025-03-21,2025-03-22,0.5,,
SYN-H031,history,G8 Recurring batch job cancellation,Incident,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Job ZFI_DAILY_UPLOAD cancelled overnight (5),Nightly bank file upload job was cancelled and reconciliation did not run.,Job cancelled; lock error on table ZFI_UPL,Restarted the job in the morning and it completed. No investigation into why it was cancelled.,Restarted job manually. Closed.,Workaround only,,Closed,2025-04-08,2025-04-09,0.5,,
SYN-H032,history,G8 Recurring batch job cancellation,Problem,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,BC-BMT-WFM,True,customer_only,Root cause for recurring ZFI_DAILY_UPLOAD cancellations,Problem ticket raised after five restarts in two months.,Lock on table ZFI_UPL,Compared job logs. Cancellations always occur between 02:00 and 02:20. Another job ZIF_BANK_IN started 02:00 after a schedule change and holds a lock on the same custom table.,Resequenced jobs with predecessor dependency so ZFI_DAILY_UPLOAD starts after ZIF_BANK_IN. Monitored for 3 weeks with no recurrence.,Confirmed root cause,Overlapping job schedule creating a table lock,Closed,2025-04-22,2025-04-25,20.0,SYN-H027; SYN-H028; SYN-H029; SYN-H030; SYN-H031,
SYN-H033,history,G9 HR / Payroll,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,HR,PY,False,shared_generalized,Payroll stops for employee with expired bank details,Payroll run stops for one employee.,Error: no valid bank details for payment period,Bank details infotype end-dated before the payroll period.,HR extended the bank details record and the payroll was rerun for the employee.,Confirmed root cause,Bank details infotype expired,Closed,2025-03-28,2025-03-29,2.0,,
SYN-H034,history,G9 HR / Payroll,Incident,High,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,HR,PY,False,shared_generalized,Payroll error: retroactive accounting limit exceeded,Backdated change to employee salary causes payroll to stop.,Retroactive accounting limit exceeded,Change was effective earlier than the earliest personal recalculation date.,Payroll lead approved moving the recalculation date; payroll rerun.,Confirmed root cause,Backdated change older than retro limit,Closed,2025-06-30,2025-07-01,3.0,,
SYN-H035,history,G9 HR / Payroll,Incident,Medium,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,HR,PT,False,shared_generalized,Leave quota not deducted after approved absence,Approved leave is not reducing the leave quota for some employees.,None; quota balance unchanged,Triggered quota recalculation manually and values corrected. Cause not identified.,Ran quota recalculation. Closed.,Unverified,,Closed,2025-08-26,2025-08-27,1.0,,
SYN-H036,history,G10 Incident evolved into change request,Incident,Low,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,SD,SD-SLS,False,shared_generalized,Cannot enter delivery instructions on sales order,Users need a delivery instructions field on the sales order header and none exists.,None,Standard header text is available but not visible in output.,Advised users to type instructions in header text. Closed as workaround; customer may raise a change.,Workaround only,,Closed,2025-02-10,2025-02-11,1.0,,
SYN-H037,history,G10 Incident evolved into change request,Change,Medium,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,SD,SD-SLS,False,shared_generalized,CR: add delivery instructions field to sales order header and output,Customer approved a change to add a custom field and show it on the delivery note.,None,"Customer approved 12 additional hours. Field added through custom fields tooling, added to the output form, tested in quality and deployed.","Custom field ZZDeliveryNote added, shown on output, tested and approved. Header text workaround no longer needed.",Confirmed root cause,"Missing business field, resolved via approved change",Closed,2025-04-15,2025-04-19,24.0,SYN-H036,
SYN-H038,history,G11 Vendor bank change,Service Request,Medium,Aurora Foods Bhd,ECC,ECC 6.0 EHP8,FI,FI-AP-AP-MD,False,shared_generalized,Change vendor bank details,Vendor requested bank detail change.,None,Changed in vendor master change transaction; change log reviewed.,Updated bank data via classic vendor change transaction with dual approval.,Confirmed root cause,,Closed,2024-12-05,2024-12-06,1.0,,
SYN-H039,history,G11 Vendor bank change,Incident,Medium,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,FI,FI-AP-AP-MD,False,shared_generalized,Vendor change transaction not available in S/4HANA,Consultant tries to change vendor bank details but transaction is blocked.,Transaction XK02 not available; use Business Partner,Vendor master maintenance moved to Business Partner in S/4HANA.,"Changed bank details through BP, confirmed change documents.",Confirmed root cause,Classic vendor transactions replaced by BP in S/4HANA,Closed,2025-09-15,2025-09-16,1.0,,
SYN-H040,history,G11 Vendor bank change,Incident,Medium,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,FI,FI-AP-AP-MD,False,shared_generalized,Vendor bank change not visible after save in BP,Updated bank account does not appear in payment proposals.,None; change pending,Change triggers four-eyes approval workflow and awaits approver.,Approver released the change through My Inbox; payment proposal then picked up the bank data.,Confirmed root cause,Four-eyes approval pending,Closed,2025-10-06,2025-10-07,2.0,SYN-H039,
SYN-Q01,incoming_test,G1 Approval flow,Incident,High,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,MM,MM-PUR-REQ,False,shared_generalized,PR approval not triggering for new document type ZNB2,New requisition document type ZNB2 skips approval and goes straight to released.,No approval task; PR status 'Released',Buyers say release strategy was previously used in ECC.,,,,Open,2026-10-05,,,,"{""expected_answer_type"": ""runbook"", ""correct_precedent_ids"": [""SYN-H002""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H001"", ""reason"": ""ECC release strategy fix; S/4 uses flexible workflow""}, {""id"": ""SYN-H003"", ""reason"": ""Public Cloud role/responsibility fix""}], ""expected_flags"": [""release_mismatch_on_lookalikes"", ""relevant_change_detected""]}"
SYN-Q02,incoming_test,G4 Billing account determination,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,SD,SD-BIL,False,shared_generalized,Billing blocked with account determination error for OTC materials,Billing documents for newly created material group fail to release to accounting.,Error in account determination: table T030 key 2000 ... ERL,Sales org 2000 recently extended.,,,,Open,2026-10-04,,,,"{""expected_answer_type"": ""diagnostic_question"", ""correct_precedent_ids"": [""SYN-H011"", ""SYN-H012""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H014"", ""reason"": ""Workaround-only closure with no root cause""}], ""expected_flags"": [""multiple_possible_causes"", ""weak_resolution_downgraded""], ""notes"": ""Should ask whether a condition record exists and whether the G/L account is extended to the company code.""}"
SYN-Q03,incoming_test,G2 Posting period not open,Incident,High,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,FI,FI-GL,True,customer_only,Posting period not open though period is open in S/4HANA,Journal entries fail with period not open while Finance confirms the period is open.,Posting period 09 2026 is not open,Started after a recent change request.,,,,Open,2026-10-03,,,,"{""expected_answer_type"": ""diagnostic_question"", ""correct_precedent_ids"": [""SYN-H008"", ""SYN-H007""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H005"", ""reason"": ""Simple period-open fix; period already confirmed open""}, {""id"": ""SYN-H006"", ""reason"": ""Variant assignment issue; verify first""}], ""expected_flags"": [""same_symptom_different_cause"", ""customization_possible""], ""notes"": ""Check asset period and custom validations before reopening period.""}"
SYN-Q04,incoming_test,G5 Authorization / missing app,Incident,Medium,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,BC,BC-SEC-LP,False,shared_generalized,AP clerk lost Manage Supplier Invoices tile after role cleanup,"After roles were cleaned up, clerks cannot see the tile.",Tile not visible,Role update done last week.,,,,Open,2026-10-06,,,,"{""expected_answer_type"": ""quick_reference"", ""correct_precedent_ids"": [""SYN-H016""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H017"", ""reason"": ""Public Cloud business roles""}, {""id"": ""SYN-H015"", ""reason"": ""GUI transaction authorization, not Fiori catalog""}], ""expected_flags"": [""minor_release_difference_still_valid""]}"
SYN-Q05,incoming_test,G6 IDoc processing,Incident,High,Delta Pharma Bhd,ECC,ECC 6.0 EHP8,FI,FI-AP,False,shared_generalized,Inbound INVOIC IDocs in status 51 after month end,Supplier invoice IDocs are failing with posting period error.,IDoc status 51: Posting period 09 2026 is not open,Period closed on working day 5.,,,,Open,2026-10-07,,,,"{""expected_answer_type"": ""runbook"", ""correct_precedent_ids"": [""SYN-H020"", ""SYN-H005""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H019"", ""reason"": ""Status 56 partner profile problem, different cause""}, {""id"": ""SYN-H022"", ""reason"": ""Status 64 workaround""}], ""expected_flags"": [""cross_scenario_link""]}"
SYN-Q06,incoming_test,G7 Custom code dumps,Incident,High,Cendana Retail Sdn Bhd,S/4HANA On-Premise,S/4HANA 2023,MM,MM-IM,True,customer_only,Custom report ZMM_GR_RPT2 dumps with unknown field after update,Report dumps with unknown field error after the last support package update.,ABAP runtime error: field MSEG-ZZSIZE unknown,Same developer team as ZMM_GR_RPT.,,,,Open,2026-10-02,,,,"{""expected_answer_type"": ""escalation"", ""correct_precedent_ids"": [""SYN-H024""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H023"", ""reason"": ""Memory dump on ECC; different error and release""}], ""expected_flags"": [""customized_system"", ""developer_handoff""]}"
SYN-Q07,incoming_test,G8 Recurring batch job cancellation,Incident,Medium,Borneo Steel Sdn Bhd,S/4HANA On-Premise,S/4HANA 2022,FI,BC-BMT-WFM,True,customer_only,Nightly upload job ZFI_UPLOAD_NIGHT cancelled with lock error,Upload job cancelled overnight; consultant plans to restart.,Job cancelled; lock error on custom table,Third time this month.,,,,Open,2026-10-08,,,,"{""expected_answer_type"": ""diagnostic_question"", ""correct_precedent_ids"": [""SYN-H032""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H027"", ""reason"": ""Restart-only workaround, no root cause""}, {""id"": ""SYN-H028"", ""reason"": ""Restart-only workaround""}, {""id"": ""SYN-H029"", ""reason"": ""Restart-only workaround""}, {""id"": ""SYN-H030"", ""reason"": ""Restart-only workaround""}, {""id"": ""SYN-H031"", ""reason"": ""Restart-only workaround""}], ""expected_flags"": [""weak_resolution_downgraded"", ""recurring_cluster"", ""suggest_problem_ticket""], ""notes"": ""Ask whether another job overlaps in the failure window. H032 applies only if confirmed.""}"
SYN-Q08,incoming_test,G10 Incident evolved into change request,Incident,Low,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,SD,SD-SLS,False,shared_generalized,Delivery instructions text missing on sales order output,A user asks again how to add delivery instructions to the sales order.,None,Previous consultant suggested header text.,,,,Open,2026-10-06,,,,"{""expected_answer_type"": ""quick_reference"", ""correct_precedent_ids"": [""SYN-H037""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H036"", ""reason"": ""Superseded workaround; field now exists""}], ""expected_flags"": [""stale_precedent_superseded""]}"
SYN-Q09,incoming_test,G11 Vendor bank change,Incident,Medium,Aurora Foods Bhd,S/4HANA On-Premise,S/4HANA 2023,FI,FI-AP-AP-MD,False,shared_generalized,Need to change vendor bank account; XK02 not available,Consultant follows the Aurora runbook but the transaction is blocked.,Transaction XK02 not available; use Business Partner,Aurora migrated to S/4HANA last year.,,,,Open,2026-10-07,,,,"{""expected_answer_type"": ""quick_reference"", ""correct_precedent_ids"": [""SYN-H039"", ""SYN-H040""], ""not_applicable_lookalikes"": [{""id"": ""SYN-H038"", ""reason"": ""ECC-era procedure""}], ""expected_flags"": [""conflicting_sources"", ""outdated_sharepoint_doc"", ""source_of_truth_is_system""], ""notes"": ""SP-001 conflicts with H039.""}"
SYN-Q10,incoming_test,G12 No precedent,Incident,Medium,Evergreen Logistics Sdn Bhd,SAP Public Cloud (S/4HANA Cloud),Public Cloud 2508,BC,BC-EWA,False,shared_generalized,Custom CDS view not visible in analytical app after transport,A transported custom CDS view for sales KPIs is not shown in the custom analytical query app.,No data; view not listed,Transport imported successfully.,,,,Open,2026-10-09,,,,"{""expected_answer_type"": ""escalation"", ""correct_precedent_ids"": [], ""not_applicable_lookalikes"": [], ""expected_flags"": [""no_precedent"", ""open_knowledge_gap""], ""notes"": ""Engine should say no usable precedent and open a knowledge gap, not force a weak match.""}"
"""


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save CSV and generate Excel .xlsx file
    csv_path = data_dir / 'synthetic_tickets.csv'
    csv_path.write_text(CSV_TEXT.strip(), encoding='utf-8')
    print(f'Wrote CSV to {csv_path}')

    xlsx_path = data_dir / 'synthetic_tickets.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Synthetic Tickets"
    reader = csv.reader(io.StringIO(CSV_TEXT.strip()))
    for row in reader:
        ws.append(row)
    wb.save(xlsx_path)
    print(f'Wrote Excel file to {xlsx_path}')

    # 2. Connect to MongoDB Atlas
    store = MongoStore(settings)
    store.initialize()
    ai = AIService(settings)

    rows = list(csv.DictReader(io.StringIO(CSV_TEXT.strip())))
    history_rows = [r for r in rows if r['dataset_role'] == 'history']
    incoming_rows = [r for r in rows if r['dataset_role'] == 'incoming_test']

    print(f'Found {len(history_rows)} historical tickets and {len(incoming_rows)} incoming test tickets.')

    # 3. Prepare Knowledge Sources from history_rows
    sources_to_index = []
    for r in history_rows:
        ticket_id = r['ticket_id']
        title = r['title']
        customer = 'General' if r['visibility'] == 'shared_generalized' else r['customer']
        app = f"{r['module']} ({r['platform']})"
        ver = r['release']
        err = r['error_message'] if r['error_message'] != 'None' else ''

        # Build comprehensive and citation-friendly content
        content_lines = [
            f"Ticket: {ticket_id} - {title}",
            f"Customer: {r['customer']} | Visibility: {r['visibility']}",
            f"System: {r['platform']} {r['release']} | Module: {r['module']} {r['component']}",
            f"Problem: {r['problem_statement']}",
        ]
        if err:
            content_lines.append(f"Error Code/Message: {err}")
        if r['investigation_notes']:
            content_lines.append(f"Investigation: {r['investigation_notes']}")
        if r['root_cause']:
            content_lines.append(f"Root Cause: {r['root_cause']}")
        if r['resolution']:
            content_lines.append(f"Resolution Procedure: {r['resolution']}")
        if r['resolution_quality']:
            content_lines.append(f"Resolution Quality: {r['resolution_quality']}")
        if r['linked_ticket_ids']:
            content_lines.append(f"Linked Tickets: {r['linked_ticket_ids']}")

        content = "\n".join(content_lines)
        stamp = now()

        validation = 'Verified' if r['resolution_quality'] == 'Confirmed root cause' else 'Reviewed'
        source = dict(
            id=ticket_id,
            title=title[:200],
            content=content,
            application=app[:100],
            version=ver[:100],
            error_code=err[:100],
            customer=customer,
            source_type='Historical ticket',
            filename='synthetic_tickets.xlsx',
            source_reference=ticket_id,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            validation=validation,
            validation_evidence={'tested': True, 'customer_confirmed': True, 'deployed': True} if validation == 'Verified' else {},
            solution_kind='Likely solution' if validation == 'Verified' else 'Workaround',
            solution=r['resolution'],
            steps=[r['resolution']] if r['resolution'] else [],
            conflicts_with=[],
            created_at=stamp,
            updated_at=stamp,
            index_status='Pending',
            index_error='',
            chunk_count=0,
            chunks=[],
            embedding_model='',
            revision=0
        )
        sources_to_index.append(source)

    # 4. Batch embed the sources
    print('Generating embeddings for historical sources...')
    all_chunks = []
    chunk_to_source = []
    for s in sources_to_index:
        s_chunks = chunks(s['content'])
        s['chunks'] = s_chunks
        s['chunk_count'] = len(s_chunks)
        for c in s_chunks:
            all_chunks.append(s['title'] + '\n' + c['text'])
            chunk_to_source.append((s, c))

    print(f'Total chunks to embed: {len(all_chunks)}')
    try:
        vectors = ai.embed(all_chunks)
        for (s, c), vec in zip(chunk_to_source, vectors):
            c['embedding'] = vec
        for s in sources_to_index:
            s['index_status'] = 'Ready'
            s['embedding_model'] = ai.config.embedding_model
            s['indexed_at'] = now()
    except Exception as exc:
        print(f'Embedding warning: {exc}. Saving sources without vector index.')
        for s in sources_to_index:
            s['index_status'] = 'Error'
            s['index_error'] = str(exc)

    # Save sources to MongoDB
    for s in sources_to_index:
        # Upsert by id
        store.db.sources.replace_one({'id': s['id']}, s, upsert=True)
    print(f'Seeded {len(sources_to_index)} Knowledge Sources into MongoDB.')

    # 5. Seed incoming test investigations
    print('Seeding incoming test investigations...')
    for r in incoming_rows:
        ticket_id = r['ticket_id']
        title = r['title']
        customer = r['customer']
        app = f"{r['module']} ({r['platform']})"
        ver = r['release']
        err = r['error_message'] if r['error_message'] != 'None' else ''
        desc = r['problem_statement']
        if r['investigation_notes']:
            desc += "\n\nInvestigation notes: " + r['investigation_notes']

        stamp = now()
        inv_item = dict(
            id=f"INV-{ticket_id}",
            ticket_id=ticket_id,
            title=title[:200],
            description=desc,
            application=app[:100],
            version=ver[:100],
            error_code=err[:100],
            customisation=r['component'] if r['customized'] == 'True' else '',
            type=r['ticket_type'] if r['ticket_type'] in ('Incident', 'Service request', 'Problem', 'Change request') else 'Incident',
            priority=r['priority'] if r['priority'] in ('Low', 'Medium', 'High', 'Critical') else 'Medium',
            customer=customer,
            status='New',
            created_at=stamp,
            updated_at=stamp,
            timeline=[
                dict(at=stamp, kind='Intake', text=f"Imported from {r['platform']} ({r['scenario_group']}). {r['problem_statement'][:100]}", author='System Import', source=ticket_id)
            ],
            analysis=None,
            decisions={},
            selected_source=None,
            outcome=None,
            revision=1
        )
        if r['ground_truth']:
            try:
                inv_item['ground_truth'] = json.loads(r['ground_truth'])
            except Exception:
                inv_item['ground_truth'] = r['ground_truth']

        store.db.investigations.replace_one({'id': inv_item['id']}, inv_item, upsert=True)

    # Also seed historical tickets as closed investigations so they show in dashboards/metrics
    for r in history_rows:
        ticket_id = r['ticket_id']
        title = r['title']
        customer = r['customer']
        app = f"{r['module']} ({r['platform']})"
        ver = r['release']
        err = r['error_message'] if r['error_message'] != 'None' else ''
        desc = r['problem_statement']

        created_stamp = f"{r['created']}T08:00:00+00:00" if r['created'] else now()
        closed_stamp = f"{r['closed']}T16:00:00+00:00" if r['closed'] else now()
        inv_item = dict(
            id=f"INV-{ticket_id}",
            ticket_id=ticket_id,
            title=title[:200],
            description=desc,
            application=app[:100],
            version=ver[:100],
            error_code=err[:100],
            customisation=r['component'] if r['customized'] == 'True' else '',
            type=r['ticket_type'] if r['ticket_type'] in ('Incident', 'Service request', 'Problem', 'Change request') else 'Incident',
            priority=r['priority'] if r['priority'] in ('Low', 'Medium', 'High', 'Critical') else 'Medium',
            customer=customer,
            status='Resolved',
            created_at=created_stamp,
            updated_at=closed_stamp,
            timeline=[
                dict(at=created_stamp, kind='Intake', text=desc[:150], author='Consultant', source=ticket_id),
                dict(at=closed_stamp, kind='Outcome', text=f"Root cause: {r['root_cause']}. Fix: {r['resolution']}", author='Consultant', source='Closed investigation')
            ],
            analysis=None,
            decisions={},
            selected_source=ticket_id,
            outcome=dict(
                status='Resolved',
                notes=r['resolution'],
                recorded_at=closed_stamp,
                selected_source=ticket_id,
                alternative_solution='',
                usefulness='Useful',
                tested=True,
                customer_confirmed=True,
                approved=True,
                developed=True,
                deployed=True,
                verified=True
            ),
            revision=1
        )
        store.db.investigations.replace_one({'id': inv_item['id']}, inv_item, upsert=True)

    print(f'Successfully seeded {len(history_rows) + len(incoming_rows)} investigations.')
    print('All data seeded successfully into MongoDB Atlas!')


if __name__ == '__main__':
    main()
