# Lock down the ordering machine

The web application protects its own logout with an administrator password and prevents navigation to other application HTML pages while its kiosk cookie is present. This does not prevent closing a browser, clearing a profile, opening OS shortcuts, or using another application.

Configure the actual machine with Windows Assigned Access and Microsoft Edge kiosk mode. Use a dedicated non-administrator Windows account. Set its start URL to https://your-campus-host/kiosk.html and configure allowed navigation, downloads, printing, browser exit/restart, keyboard shortcuts and access to Settings through managed policy. Keep the OS administrator password separate from the application password.

Follow Microsoft's current instructions rather than treating browser fullscreen flags as an OS security boundary:

- [Assigned Access kiosk quickstart](https://learn.microsoft.com/en-us/windows/configuration/assigned-access/quickstart-kiosk)
- [Microsoft Edge kiosk mode](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-configure-kiosk-mode)

Provision the scanner worker as an appropriate protected native service that the kiosk user cannot edit. Verify it can access the physical USB/serial scanner in the selected Assigned Access configuration. Keep scanner credentials off the kiosk webpage and out of browser storage.

## Printing

The web UI uses the browser print mechanism with an 80 mm receipt layout. Select the correct thermal printer and paper size, disable browser headers/footers, and validate readability and margins on actual paper. Managed silent printing requires browser/printer deployment configuration or a future trusted native print adapter; it is not supplied by JavaScript.

After the print dialog returns, including cancellation, the station clears the receipt and returns to the menu. Browsers cannot reliably confirm physical paper delivery. The UI does not claim printing succeeded. If paper is jammed or missing, staff retrieves a paid order's stored receipt through Admin → Orders & receipts and prints a copy. The original payment is never repeated for printing problems.

Accept the machine only after testing reboot, browser crash, profile reset, offline network, session expiry, scanner disconnect, printer offline/out of paper, accessibility and attempted navigation out of the kiosk. The completed-receipt timeout is 30 seconds; abandoned cart timeout is 60 seconds. A pending or uncertain payment is never discarded as an ordinary idle cart.
