# -*- coding: utf-8 -*-
"""QGIS plugin for searching OS Places addresses."""

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgsVertexMarker

from . import resources  # noqa: F401  (registers Qt resources)
from .addresssearch_dialog import OS_search_for_addressesDialog


OS_API_SCHEME = "https"
OS_API_HOST = "api.os.uk"
OS_API_BASE = f"{OS_API_SCHEME}://{OS_API_HOST}/search/places/v1"
REQUEST_TIMEOUT_SECONDS = 20
BBOX_PAGE_SIZE = 100
BBOX_MAX_RECORDS = 2000
BBOX_MAX_AREA_SQUARE_METRES = 1_000_000
AUTH_SETTING_KEY = "addresssearch/os_api_key"
LEGACY_SETTING_KEY = "addresssearch/apikey"


class OS_search_for_addresses:
    """QGIS plugin implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&OS search for addresses")
        self.first_start = True
        self.dlg = None
        self.address_results: List[Dict[str, Any]] = []
        self.created_markers = []

        locale_value = QSettings().value("locale/userLocale", "en") or "en"
        locale = str(locale_value)[:2]
        locale_path = os.path.join(
            self.plugin_dir, "i18n", f"OS_search_for_addresses_{locale}.qm"
        )
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("OS_search_for_addresses", message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        self.add_action(
            ":/plugins/addresssearch/icon.png",
            text=self.tr("OS address search"),
            callback=self.run,
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        self.clear_markers()
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def _message(self, text, level=Qgis.MessageLevel.Info, duration=7):
        self.iface.messageBar().pushMessage(
            text, level=level, duration=duration
        )

    def _api_key(self):
        return self.dlg.APIKEY.text().strip() if self.dlg else ""

    def _request_json(self, endpoint, parameters):
        """Request JSON from the fixed OS API origin only."""
        if endpoint not in {"find", "postcode", "bbox"}:
            raise ValueError("Unsupported OS Places endpoint")

        query = urllib.parse.urlencode(parameters)
        url = f"{OS_API_BASE}/{endpoint}?{query}"
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != OS_API_SCHEME or parsed.hostname != OS_API_HOST:
            raise ValueError("Refusing request to an unexpected URL")

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "QGIS-OS-Address-Search/1.5.3",
            },
            method="GET",
        )
        # The scheme and hostname are fixed and validated above; redirects are
        # still restricted by the standard HTTPS handler. nosec B310
        with urllib.request.urlopen(  # nosec B310
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            if response.geturl().split(":", 1)[0].lower() != "https":
                raise ValueError("Refusing a non-HTTPS redirect")
            return json.loads(response.read().decode("utf-8"))

    def _run_request(self, endpoint, parameters):
        try:
            return self._request_json(endpoint, parameters)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            socket.timeout,
        ) as exc:
            self._message(
                f"OS Places request failed: {exc}", Qgis.MessageLevel.Warning)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._message(
                f"Unexpected OS Places response: {exc}",
                Qgis.MessageLevel.Warning)
        return None

    def _set_address_results(self, payload):
        results = payload.get(
            "results",
            []) if isinstance(
            payload,
            dict) else []
        self.address_results = []
        for result in results:
            dpa = result.get("DPA", {})
            if all(key in dpa for key in ("ADDRESS", "LNG", "LAT")):
                self.address_results.append(dpa)

        self.dlg.comboBoxadd.clear()
        self.dlg.comboBoxadd.addItems(
            [str(item.get("ADDRESS", "")) for item in self.address_results]
        )
        if not self.address_results:
            self._message("No matching addresses were returned.",
                          Qgis.MessageLevel.Info)

    def getadd(self):
        api_key = self._api_key()
        if not api_key:
            self._message("Please enter an OS API key",
                          Qgis.MessageLevel.Warning)
            return

        query = ", ".join(
            part
            for part in (
                self.dlg.sadd.text().strip(),
                self.dlg.spostcode.text().strip(),
            )
            if part
        )
        if not query:
            self._message("Please enter an address or postcode",
                          Qgis.MessageLevel.Warning)
            return

        payload = self._run_request(
            "find",
            {
                "dataset": "DPA",
                "key": api_key,
                "output_srs": "EPSG:4326",
                "minmatch": "0.6",
                "query": query,
            },
        )
        if payload is not None:
            self._set_address_results(payload)

    def serpostcode(self):
        api_key = self._api_key()
        postcode = self.dlg.spostcode.text().strip()
        if not api_key:
            self._message("Please enter an OS API key",
                          Qgis.MessageLevel.Warning)
            return
        if len(postcode) < 3:
            self._message("Enter more of the postcode",
                          Qgis.MessageLevel.Warning)
            return

        payload = self._run_request(
            "postcode",
            {"postcode": postcode, "key": api_key, "output_srs": "EPSG:4326"},
        )
        if payload is not None:
            self._set_address_results(payload)

    def where(self):
        index = self.dlg.comboBoxadd.currentIndex()
        if index < 0 or index >= len(self.address_results):
            self._message("Select an address result first",
                          Qgis.MessageLevel.Warning)
            return

        selected = self.address_results[index]
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        destination_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(
            source_crs,
            destination_crs,
            QgsProject.instance().transformContext(),
        )
        point = transform.transform(
            QgsPointXY(float(selected["LNG"]), float(selected["LAT"]))
        )

        canvas = self.iface.mapCanvas()
        self.clear_markers(refresh=False)
        scale = 300.0
        canvas.setExtent(
            QgsRectangle(
                point.x() - scale,
                point.y() - scale,
                point.x() + scale,
                point.y() + scale,
            )
        )
        marker = QgsVertexMarker(canvas)
        marker.setIconSize(15)
        marker.setPenWidth(2)
        marker.setCenter(point)
        self.created_markers.append(marker)
        canvas.refresh()

    def clear_markers(self, refresh=True):
        canvas = self.iface.mapCanvas()
        scene = canvas.scene()
        for marker in self.created_markers:
            if marker.scene() is scene:
                scene.removeItem(marker)
        self.created_markers.clear()
        if refresh:
            canvas.refresh()

    # Keep the existing signal target name used by the UI connection.
    def clearm(self):
        self.clear_markers()

    def getalladd(self):
        api_key = self._api_key()
        if not api_key:
            self._message("Please enter an OS API key",
                          Qgis.MessageLevel.Warning)
            return

        canvas = self.iface.mapCanvas()
        source_crs = canvas.mapSettings().destinationCrs()
        extent = canvas.extent()
        context = QgsProject.instance().transformContext()

        # OS Places limits BBOX requests to 1 km². Measure the current view in
        # British National Grid before making any API requests, so a town-wide
        # view is rejected immediately.
        area_transform = QgsCoordinateTransform(
            source_crs, QgsCoordinateReferenceSystem("EPSG:27700"), context
        )
        area_lower_left = area_transform.transform(
            QgsPointXY(extent.xMinimum(), extent.yMinimum())
        )
        area_upper_right = area_transform.transform(
            QgsPointXY(extent.xMaximum(), extent.yMaximum())
        )
        width = abs(area_upper_right.x() - area_lower_left.x())
        height = abs(area_upper_right.y() - area_lower_left.y())
        area = width * height
        if area > BBOX_MAX_AREA_SQUARE_METRES:
            self._message(
                "Map view is too large. Zoom in until the visible area "
                "is 1 km² or less.",
                Qgis.MessageLevel.Warning,
                duration=10,
            )
            return

        destination_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(
            source_crs, destination_crs, context)
        lower_left = transform.transform(
            QgsPointXY(extent.xMinimum(), extent.yMinimum()))
        upper_right = transform.transform(
            QgsPointXY(extent.xMaximum(), extent.yMaximum()))
        bbox = ",".join(
            map(
                str,
                (
                    lower_left.y(),
                    lower_left.x(),
                    upper_right.y(),
                    upper_right.x(),
                ),
            )
        )

        all_results = []
        offset = 0
        while offset < BBOX_MAX_RECORDS:
            payload = self._run_request(
                "bbox",
                {
                    "key": api_key,
                    "bbox": bbox,
                    "dataset": "DPA",
                    "maxresults": BBOX_PAGE_SIZE,
                    "offset": offset,
                    "output_srs": "EPSG:4326",
                    "srs": "EPSG:4326",
                },
            )
            if payload is None:
                return

            page_results = payload.get("results", [])
            all_results.extend(page_results)
            if len(page_results) < BBOX_PAGE_SIZE:
                break
            offset += BBOX_PAGE_SIZE

        features = []
        seen_uprns = set()
        for result in all_results:
            dpa = dict(result.get("DPA", {}))
            if "LNG" not in dpa or "LAT" not in dpa:
                continue
            uprn = str(dpa.get("UPRN", ""))
            if uprn and uprn in seen_uprns:
                continue
            if uprn:
                seen_uprns.add(uprn)
            dpa.pop("BLPU_STATE_CODE", None)
            features.append(
                {
                    "type": "Feature",
                    "properties": dpa,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [dpa["LNG"], dpa["LAT"]],
                    },
                }
            )

        if not features:
            self._message(
                "No addresses were found in the current map view.",
                Qgis.MessageLevel.Info)
            return

        geojson = json.dumps(
            {"type": "FeatureCollection", "features": features})
        layer = QgsVectorLayer(
            geojson, f"OS addresses ({
                len(features)})", "ogr")
        if not layer.isValid():
            self._message(
                "QGIS could not create the address layer.",
                Qgis.MessageLevel.Warning)
            return
        QgsProject.instance().addMapLayer(layer)

        if len(all_results) >= BBOX_MAX_RECORDS:
            self._message(
                f"Loaded the first {BBOX_MAX_RECORDS} addresses. "
                "Zoom in for a complete result.",
                Qgis.MessageLevel.Warning,
                duration=10,
            )
        else:
            self._message(
                f"Loaded {len(features)} addresses.",
                Qgis.MessageLevel.Success,
            )

    @staticmethod
    def _read_auth_setting(auth_manager, key, default="", decrypt=True):
        """Read an authentication setting across supported QGIS versions."""
        reader = getattr(auth_manager, "authSetting", None)
        if reader is None:
            reader = getattr(auth_manager, "getAuthSetting", None)
        if reader is None:
            raise AttributeError(
                "QGIS authentication manager cannot read settings")
        return reader(key, default, decrypt)

    @staticmethod
    def _store_auth_setting(auth_manager, key, value, encrypt=True):
        """Store an authentication setting across supported QGIS versions."""
        writer = getattr(auth_manager, "storeAuthSetting", None)
        if writer is None:
            writer = getattr(auth_manager, "setAuthSetting", None)
        if writer is None:
            raise AttributeError(
                "QGIS authentication manager cannot store settings")
        return bool(writer(key, value, encrypt))

    def storekey(self):
        api_key = self._api_key()
        if not api_key:
            self._message("Please enter an OS API key",
                          Qgis.MessageLevel.Warning)
            return

        try:
            auth_manager = QgsApplication.authManager()
            saved = self._store_auth_setting(
                auth_manager, AUTH_SETTING_KEY, api_key, True
            )
        except (AttributeError, RuntimeError, TypeError) as exc:
            self._message(
                f"The API key could not be saved securely: {exc}",
                Qgis.MessageLevel.Critical,
                duration=10,
            )
            return

        if not saved:
            self._message(
                "The API key could not be saved. Check the QGIS "
                "Authentication master password.",
                Qgis.MessageLevel.Critical,
            )
            return

        QgsSettings().remove(LEGACY_SETTING_KEY)
        self._message(
            "OS API key saved in the encrypted QGIS Authentication Database.",
            Qgis.MessageLevel.Success,
        )

    def readkey(self):
        """Load the key without preventing the dialog from opening."""
        try:
            auth_manager = QgsApplication.authManager()
            api_key = str(
                self._read_auth_setting(
                    auth_manager, AUTH_SETTING_KEY, "", True
                )
                or ""
            )
        except (AttributeError, RuntimeError, TypeError) as exc:
            self.dlg.APIKEY.clear()
            self._message(
                f"The encrypted API key could not be loaded: {exc}",
                Qgis.MessageLevel.Warning,
                duration=10,
            )
            return

        # One-time migration from version 1.5.0 and earlier, where the key was
        # saved as plaintext in QgsSettings.
        if not api_key:
            legacy_key = str(QgsSettings().value(LEGACY_SETTING_KEY, "") or "")
            if legacy_key:
                try:
                    migrated = self._store_auth_setting(
                        auth_manager, AUTH_SETTING_KEY, legacy_key, True
                    )
                except (AttributeError, RuntimeError, TypeError):
                    migrated = False

                if migrated:
                    QgsSettings().remove(LEGACY_SETTING_KEY)
                    api_key = legacy_key
                    self._message(
                        "Existing API key migrated to encrypted QGIS storage.",
                        Qgis.MessageLevel.Success,
                    )
                else:
                    self._message(
                        "A legacy API key was found but could not be "
                        "migrated securely.",
                        Qgis.MessageLevel.Warning,
                        duration=10,
                    )

        self.dlg.APIKEY.setText(api_key)

    def run(self):
        if self.first_start:
            self.first_start = False
            self.dlg = OS_search_for_addressesDialog(self.iface.mainWindow())
            self.dlg.pushButtongetadd.clicked.connect(self.getadd)
            self.dlg.zoomad.clicked.connect(self.where)
            self.dlg.clearm.clicked.connect(self.clearm)
            self.dlg.getalladd.clicked.connect(self.getalladd)
            self.dlg.savekey.clicked.connect(self.storekey)
            self.dlg.loadkey.clicked.connect(self.readkey)
            self.dlg.serpostcode.clicked.connect(self.serpostcode)
            self.readkey()

        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
        # exec() exists in Qt 5 and Qt 6; exec_() was removed in Qt 6.
        self.dlg.exec()
