# Changelog


## 1.5.6 - 2026-07-17

- Updated QGIS message-level enums to the Qt6-compatible scoped `Qgis.MessageLevel` form.
- Resolved all 22 Qt6 compatibility findings reported by the QGIS plugin validator.


## 1.5.5

- Fixed API-key field echo mode on Qt6/QGIS 4.

## 1.5.4

- Fixed plugin loading in QGIS 4 / Qt6 by changing the generated resource module to use `qgis.PyQt` instead of importing PyQt5 directly.
- Rechecked the complete release package for direct PyQt5 and PyQt6 imports.

## 1.5.3

- Prepared the package for QGIS Plugin Repository submission.
- Added resilient QGIS 3/QGIS 4 authentication-setting wrappers.
- Prevented authentication-database errors from blocking the plugin dialog.
- Added repository, tracker, homepage, licence and release documentation.
- Removed development-only files from the release package.
- Updated the plugin icon to the recommended 64 × 64 size.

## 1.5.2

- Fixed encrypted authentication-setting access in QGIS 3.40.

## 1.5.1

- Masked the API key field.
- Stored the API key in the encrypted QGIS Authentication Database.
- Migrated and removed legacy plaintext settings.
- Added paged BBOX loading up to 2,000 records.
- Added the 1 km² current-view limit.

## 1.5.0

- Added QGIS 3 and QGIS 4 compatibility changes.
- Restricted network requests to the expected HTTPS OS API origin.
- Removed development upload scripts and other flagged release files.
