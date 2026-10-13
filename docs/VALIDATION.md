# Prototype validation

Validated locally on 13 October 2026.

- **21 automated tests passed** using Python unittest, including HTTP requests to a temporary loopback service. Test databases are isolated from working data.
- **JavaScript syntax check passed** with `node --check static/app.js`.
- **Browser workflow passed:** sample ticket intake, context review, chronological communications, investigation creation, evidence search, original source inspection, test note, recommendation invalidation, refreshed search, solution selection and recorded outcome.
- **Negative browser check passed:** selecting Resolved without testing and customer confirmation displayed the API validation error and retained the form contents.
- **Persistence verified:** restarting the service and reloading retained the created case and its evidence.
- **Knowledge empty state verified:** an unmatched query displays a clear empty result; clearing the query restores sources.
- **Insights verified:** the saved outcome updates case counts and consultant usefulness feedback.
- **Responsive check passed:** the 390 px viewport fits without page-level horizontal overflow. Icon-only navigation retains accessible names. The normal viewport was restored afterward.
- **Browser error log:** no JavaScript errors observed in the tested session.

One clearly titled `[Demo QA]` investigation remains in the working local database to demonstrate the tested flow. Its notes and outcome explicitly state that validation was simulated and no real SAP system was changed. It is not included in source control. The screenshot in `dashboard-preview.jpg` captures the resulting workspace.

These checks validate the local prototype's behavior. They do not establish retrieval accuracy, business time savings, enterprise security certification, SAP procedural correctness or live connector functionality.
