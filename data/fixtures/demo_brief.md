From: Maria (Ops Director, GreenLeaf Logistics)
Subject: new app?? notes from our call

hi team — as discussed, rough notes, sorry for the mess:

we need a web app for our dispatchers + a mobile app for drivers. drivers should login with their work email, and our IT asked if we can do SSO with Azure AD?? not sure yet, maybe later.

- dispatchers manage jobs, drivers, vehicles in an admin back office (create/edit/list, search)
- dashboard for the dispatcher with today's jobs, map with driver positions
- must integrate with our ERP (SAP Business One) to import orders every 15 min and push back delivery status
- maps integration for routes + ETA (google maps probably)
- customers get SMS + email notifications when the driver is on the way
- proof of delivery: photo + signature in the driver app. Possibly we want automatic damage detection on the photos with some AI model? nice to have
- monthly KPI reports for management (on-time %, jobs per driver), export to excel
- migrate ~40k historical jobs from our old Access database
- payments: no, invoicing stays in SAP. out of scope.
- GDPR: drivers' location data must be deletable on request

Timeline: pilot in 4 months. Budget not fixed.
