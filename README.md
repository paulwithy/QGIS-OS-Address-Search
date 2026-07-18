# OS Search for Addresses

A QGIS plugin for searching OS Places addresses using an OS Data Hub API key.

## Features

- Search by address and postcode.
- Zoom to a selected result and add a temporary map marker.
- Add addresses in the current map view as a QGIS point layer.
- Page through OS Places BBOX results up to a 2,000-address safety limit.
- Reject map views larger than 1 km² before making a BBOX request.
- Store the API key in the encrypted QGIS Authentication Database.
- Compatible with QGIS 3.22+ and QGIS 4.x.

## Installation

Download the release ZIP and install it using **Plugins → Manage and Install Plugins → Install from ZIP**.

## API key

Create an OS Data Hub project with access to the OS Places API, then paste the API key into the plugin and select **Save key**. QGIS may ask you to create or unlock the Authentication Database master password.

The plugin masks the key in its interface. The saved key is encrypted by QGIS and is not written to the plugin files.

## Current map view

The OS Places BBOX service limits requests to a maximum area of 1 km². The plugin blocks larger views and asks the user to zoom in. Results are loaded in pages of 100, with a maximum of 2,000 addresses per operation.

## Support

Report issues at:
https://github.com/paulwithy/QGIS-OS-Address-Search/issues

## Licence

GNU General Public License v2.0 or later.
