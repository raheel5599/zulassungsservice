# TARIQ Office

React/TypeScript Office application based on all ten images in TARIQ_Office_Vorlagen.zip. Uses the original Logo UG.png, copied unchanged to public/logo-ug.png.

## Start and build

Run `npm ci` and `npm run build` inside office. Development: `npm run dev`.

## Included views

Dashboard, order list and status drawer, six-step new-order form, customers, document review, tours, invoices, license plate production, staff, message drafts and settings. Lists support search, row selection and their primary state changes.

## Data and access

This is a frontend working version with fictional sample data. Orders, customers, document metadata, tours, invoice statuses, plate production, staff and settings are stored in this browser's localStorage. There is no shared database, authentication, server upload, payment processing or live messaging yet. Staff role changes do not enforce access restrictions. Invoice export is CSV/text, not an issued accounting document. Document upload records metadata only. No message is sent to a real recipient.

## Deployment

The manual office-deploy.yml workflow connects to the confirmed Hetzner host as fpadmin. SSH secrets remain in GitHub Actions. Docker publishes port 8091; ensure the host/network firewall permits the intended access. Use only sample data until authentication and HTTPS have been implemented.

Reference artwork in public/office-reference.webp is used as clipped decorative background, while the application UI is rendered by React.
