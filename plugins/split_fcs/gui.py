"""GUI of the 'Split concatenated FCS' tool."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QWidget

from cytoflowgui.api import ToolPlugin
from cytoflowgui.services import fcs, mapfiles
from cytoflowgui.widgets import MarkerSelector

SPLIT_MODES = [
    ("None", "none"),
    ("File", "file"),
    ("Cluster", "cluster"),
    ("Cluster x File", "cluster_file"),
    ("File x Cluster", "file_cluster"),
]
FILE_PATTERNS = ["sample_no", "sample", "file_no"]       # tried in this order
CLUSTER_PATTERNS = ["cluster", "phenograph", "flowsom"]    # tried in this order
FCS_FILTER = "FCS files (*.fcs);;All files (*)"
MAP_FILTER = "Mapping files (*.xlsx *.xlsm *.csv *.tsv *.txt);;All files (*)"
COLORS = {True: "#2e7d32", False: "#c62828", None: "gray"}


class SplitFcsTool(ToolPlugin):
    def build_ui(self):
        self.intro.setText(
            "Parse a concatenated, clustered FCS file, extract features per file and cluster,\n"
            "and optionally split the cells into FCS files.")
        self._channels: list[fcs.Channel] = []

        last_dir = lambda: str(self.setting("last_fcs_dir", ""))  # noqa: E731
        fcs_dir = lambda: (str(Path(self.fcs.path()).parent) if self.fcs.path() else last_dir())  # noqa: E731

        self.fcs = self.input_picker("fcs_file", FCS_FILTER, start_dir=last_dir)   # last used FCS folder
        self.file_ch = QComboBox()
        self._file_info: mapfiles.MapInfo | None = None
        self._cluster_info: mapfiles.MapInfo | None = None
        self.file_map = self.input_picker("file_map_file", MAP_FILTER, start_dir=fcs_dir)
        self.file_map.edit.setPlaceholderText("optional")
        self.file_name = QComboBox()                               # naming column of the pheno tab
        self.file_name.setMinimumWidth(200)
        self.file_name.setEnabled(False)
        self.file_status = self._status_label()
        name_row = QWidget()
        nl = QHBoxLayout(name_row)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(self.file_name)
        nl.addWidget(self.file_status, 1)
        self.cluster_ch = QComboBox()
        self.cluster_map = self.input_picker("cluster_map_file", MAP_FILTER, start_dir=fcs_dir)
        self.cluster_map.edit.setPlaceholderText("optional")
        self.cluster_status = self._status_label()
        for c in (self.file_ch, self.cluster_ch):
            c.setMinimumWidth(240)

        self.cb_xlsx, self.cb_tsv = QCheckBox("XLSX"), QCheckBox("TSV")
        self.cb_xlsx.setChecked(True)
        fmt = QWidget()
        fl = QHBoxLayout(fmt)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.cb_xlsx)
        fl.addWidget(self.cb_tsv)
        fl.addStretch(1)

        self.mode = QComboBox()
        for label, key in SPLIT_MODES:
            self.mode.addItem(label, key)

        self.heat_markers = MarkerSelector()
        self.report_markers = MarkerSelector()
        self.heat_markers.setToolTip("Markers whose MFI is shown in the cluster heatmap")
        self.report_markers.setToolTip("Markers whose MFI is reported per cluster and file")

        f = self.form
        f.addRow("Concatenated FCS file:", self.fcs)
        f.addRow("File channel:", self.file_ch)
        f.addRow("File mapping (XLSX/CSV):", self.file_map)
        f.addRow("File name column:", name_row)
        f.addRow("Cluster channel:", self.cluster_ch)
        f.addRow("Cluster mapping (XLSX/CSV):", self.cluster_map)
        f.addRow("Cluster mapping check:", self.cluster_status)
        f.addRow("Output tables:", fmt)
        f.addRow("Split FCS mode:", self.mode)
        self._add_top_row("Heatmap markers (MFI):", self.heat_markers)
        self._add_top_row("Report markers (MFI):", self.report_markers)

        self.fcs.changed.connect(self._load_channels)
        self.file_ch.currentIndexChanged.connect(lambda _: (self._refresh_markers(), self._inspect_file()))
        self.cluster_ch.currentIndexChanged.connect(lambda _: (self._refresh_markers(), self._inspect_cluster()))
        self.file_map.changed.connect(lambda _: self._inspect_file())
        self.cluster_map.changed.connect(lambda _: self._inspect_cluster())
        self._inspect_file()
        self._inspect_cluster()

    def _add_top_row(self, text: str, widget: QWidget):
        """Form row whose label stays at the top of a tall widget."""
        row = self.form.rowCount()
        self.form.addRow(QLabel(text), widget)
        item = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item is not None:
            item.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    # ---- channels and markers
    def _load_channels(self, path: str):
        combos = (self.file_ch, self.cluster_ch)
        for c in combos:
            c.blockSignals(True)
            c.clear()
        self._channels = []
        try:
            if not path:
                return
            try:
                self._channels = fcs.read_channels(path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "FCS error", f"Cannot read FCS header:\n{e}")
                return
            self.set_setting("last_fcs_dir", str(Path(path).resolve().parent))   # remembered for next time
            for ch in self._channels:
                for c in combos:
                    c.addItem(ch.label, ch.name)
            for combo, patterns in ((self.file_ch, FILE_PATTERNS), (self.cluster_ch, CLUSTER_PATTERNS)):
                guess = fcs.guess_channel(self._channels, patterns)
                if guess and (i := combo.findData(guess)) >= 0:
                    combo.setCurrentIndex(i)
        finally:
            for c in combos:
                c.blockSignals(False)
            self._refresh_markers()
            self._inspect_file()
            self._inspect_cluster()

    def _refresh_markers(self):
        """Marker lists come from $PnS of the FCS, minus the file and cluster channels."""
        pairs = fcs.markers(self._channels, [self.file_ch.currentData(), self.cluster_ch.currentData()])
        self.heat_markers.set_markers(pairs)
        self.report_markers.set_markers(pairs)

    # ---- mapping files
    def _status_label(self) -> QLabel:
        lab = QLabel()
        lab.setWordWrap(True)
        return lab

    @staticmethod
    def _set_status(label: QLabel, ok: bool | None, text: str):
        label.setText(("✔ " if ok else "✖ " if ok is False else "") + text)
        label.setStyleSheet(f"color: {COLORS[ok]}")

    @staticmethod
    def _inspect(fn, path: str, channel: str) -> mapfiles.MapInfo:
        try:
            return fn(path, channel)
        except Exception as e:  # noqa: BLE001
            return mapfiles.MapInfo(ok=False, message=f"Cannot read the file: {e}")

    def _inspect_file(self):
        path, ch = self.file_map.path(), self.file_ch.currentData()
        prev = self.file_name.currentData()
        box = self.file_name
        box.blockSignals(True)
        box.clear()
        box.setEnabled(False)
        self._file_info = None
        if not path:
            self._set_status(self.file_status, None, "No mapping: files are identified by number")
        elif not ch:
            self._set_status(self.file_status, None, "Load the FCS file first")
        elif not Path(path).is_file():
            self._set_status(self.file_status, False, "File not found")
        else:
            info = self._file_info = self._inspect(mapfiles.inspect_file_map, path, ch)
            if info.ok and info.kind == "table":
                box.addItem("— select —", None)
                for c in info.columns:
                    box.addItem(c, c)
                pick = prev if prev in info.columns else info.suggested   # keep the user's choice
                if pick:
                    box.setCurrentIndex(box.findData(pick))
                box.setEnabled(True)
            elif info.ok:
                box.addItem("(second column)", None)
            self._set_status(self.file_status, info.ok, info.message)
        box.blockSignals(False)

    def _inspect_cluster(self):
        path, ch = self.cluster_map.path(), self.cluster_ch.currentData()
        self._cluster_info = None
        if not path:
            self._set_status(self.cluster_status, None, "No mapping: clusters are identified by number")
        elif not ch:
            self._set_status(self.cluster_status, None, "Load the FCS file first")
        elif not Path(path).is_file():
            self._set_status(self.cluster_status, False, "File not found")
        else:
            info = self._cluster_info = self._inspect(mapfiles.inspect_cluster_map, path, ch)
            self._set_status(self.cluster_status, info.ok, info.message)

    # ---- validation and parameters
    def apply_parameters(self, p: dict) -> list[str]:
        warns = []
        path = p.get("fcs_file") or ""
        self.fcs.edit.setText(path)
        if path and Path(path).is_file():
            self._load_channels(path)
        elif path:
            warns.append(f"FCS file not found: {path}")
        for combo, key in ((self.file_ch, "file_channel"), (self.cluster_ch, "cluster_channel")):
            value = p.get(key)
            if value and combo.findData(value) >= 0:
                combo.setCurrentIndex(combo.findData(value))
            elif value:
                warns.append(f"Channel '{value}' not found in the FCS file")
        self.file_map.edit.setText(p.get("file_map_file") or "")
        self.cluster_map.edit.setText(p.get("cluster_map_file") or "")
        self._inspect_file()
        self._inspect_cluster()
        column = p.get("file_name_column")
        if column:
            if self.file_name.findData(column) >= 0:
                self.file_name.setCurrentIndex(self.file_name.findData(column))
            else:
                warns.append(f"File name column '{column}' not found in the mapping file")
        formats = p.get("table_formats") or []
        self.cb_xlsx.setChecked("xlsx" in formats)
        self.cb_tsv.setChecked("tsv" in formats)
        if self.mode.findData(p.get("split_mode")) >= 0:
            self.mode.setCurrentIndex(self.mode.findData(p.get("split_mode")))
        for selector, key in ((self.heat_markers, "mfi_heatmap_markers"), (self.report_markers, "mfi_report_markers")):
            missing = selector.set_selected(p.get(key) or [])
            if missing:
                warns.append(f"Markers not found: {', '.join(missing)}")
        return warns

    def validate(self):
        fcs_f, smap, cmap = self.fcs.path(), self.file_map.path(), self.cluster_map.path()
        if not fcs_f or not Path(fcs_f).is_file():
            return "Select an existing concatenated FCS file."
        if self.file_ch.currentData() is None or self.cluster_ch.currentData() is None:
            return "Select the file and cluster channels."
        if self.file_ch.currentData() == self.cluster_ch.currentData():
            return "File and cluster channels must differ."
        if smap and not Path(smap).is_file():
            return "The file mapping does not exist."
        if cmap and not Path(cmap).is_file():
            return "The cluster mapping file does not exist."
        self._inspect_file()
        self._inspect_cluster()
        if smap:
            info = self._file_info
            if not info or not info.ok:
                return f"File mapping: {info.message if info else 'invalid file'}"
            if info.kind == "table" and not self.file_name.currentData():
                return "Select the column holding the file names."
        if cmap and not (self._cluster_info and self._cluster_info.ok):
            return f"Cluster mapping: {self._cluster_info.message if self._cluster_info else 'invalid file'}"
        if not (self.cb_xlsx.isChecked() or self.cb_tsv.isChecked()):
            return "Select at least one output table format."
        return None

    def collect_parameters(self) -> dict:
        fcs_f, smap, cmap = Path(self.fcs.path()), self.file_map.path(), self.cluster_map.path()
        self.set_setting("last_fcs_dir", str(fcs_f.resolve().parent))
        pairs = dict(self.heat_markers.selected_pairs() + self.report_markers.selected_pairs())
        si, ci = (self._file_info if smap else None), (self._cluster_info if cmap else None)
        return {
            "fcs_file": str(fcs_f.resolve()),
            "file_channel": self.file_ch.currentData(),
            "file_map_file": str(Path(smap).resolve()) if smap else None,
            "file_map_format": si.kind if si else None,           # "simple" | "table"
            "file_map_sheet": si.sheet if si else None,           # "pheno" (table)
            "file_map_id_column": si.id_column if si else None,   # column matching file_channel (table)
            "file_name_column": self.file_name.currentData() if si and si.kind == "table" else None,
            "cluster_channel": self.cluster_ch.currentData(),
            "cluster_map_file": str(Path(cmap).resolve()) if cmap else None,
            "cluster_map_format": ci.kind if ci else None,          # "simple" | "table"
            "cluster_map_sheet": ci.sheet if ci else None,          # "clusters" (table): rows where
                                                                    # clustering_id == cluster_channel
            "table_formats": [k for k, cb in (("xlsx", self.cb_xlsx), ("tsv", self.cb_tsv))
                              if cb.isChecked()],
            "split_mode": self.mode.currentData(),
            "mfi_heatmap_markers": self.heat_markers.selected(),     # empty list = all markers
            "mfi_report_markers": self.report_markers.selected(),    # empty list = all markers
            "marker_channels": pairs,                                # marker ($PnS) -> channel ($PnN)
        }
