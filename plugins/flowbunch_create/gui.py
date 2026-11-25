"""GUI of the 'Create flowBunch' tool."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit

from cytoflowgui.api import ToolPlugin

CYTOMETERS = [("Spectral", "spectral"), ("Flow", "flow"), ("Mass", "mass"), ("None", "none")]
# language of the dates, passed to fb_update_pheno_dates: code -> long name shown in the GUI
LANGUAGES = {
    "en": "English", "fr": "French", "de": "German", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "nl": "Dutch",
}


def _number_or_text(text: str):
    """Cofactor: a number when it looks like one, else the text; None when empty (default used)."""
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return text
    return int(value) if value.is_integer() else value


class FlowBunchCreateTool(ToolPlugin):
    def build_ui(self):
        self.intro.setText(
            "Scan a folder of FCS files and create a flowBunch object, with the\n"
            "phenotype and panel tables and summary plots.")

        last_dir = lambda: str(self.setting("last_fcs_dir", ""))  # noqa: E731
        self.fcs_dir = self.input_picker("fcs_dir")                # a folder, see [[inputs]]
        self.fcs_dir.start_dir = last_dir
        self.fcs_dir.edit.setPlaceholderText("folder holding the FCS files")
        self.fb_name = QLineEdit()
        self.fb_name.setPlaceholderText("name of the flowBunch, e.g. the project")
        self.cytometer = QComboBox()
        for label, key in CYTOMETERS:
            self.cytometer.addItem(label, key)
        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.cofactor = QLineEdit()
        self.cofactor.setPlaceholderText("optional, empty = default of the cytometer")
        self.test_mode = QCheckBox("Test mode: do not write the flowBunch to disk")

        f = self.form
        f.addRow("FCS folder:", self.fcs_dir)
        f.addRow("flowBunch name:", self.fb_name)
        f.addRow("Cytometer:", self.cytometer)
        f.addRow("Language for date:", self.language)
        f.addRow("Cofactor:", self.cofactor)
        f.addRow("", self.test_mode)

        self._name_touched = False
        self.fb_name.textEdited.connect(lambda _: setattr(self, "_name_touched", True))
        self.fcs_dir.changed.connect(self._folder_changed)

    def _folder_changed(self, path: str):
        """Propose the folder name as flowBunch name, until the user types one."""
        p = Path(path)
        if p.is_dir():
            self.set_setting("last_fcs_dir", str(p.resolve().parent))
            if not self._name_touched or not self.fb_name.text().strip():
                self.fb_name.setText(re.sub(r"[^A-Za-z0-9._-]+", "_", p.name).strip("_"))
                self._name_touched = False

    def apply_parameters(self, p: dict) -> list[str]:
        warns = []
        folder = p.get("fcs_dir") or ""
        self.fcs_dir.edit.setText(folder)
        if folder and not Path(folder).is_dir():
            warns.append(f"FCS folder not found: {folder}")
        self.fb_name.setText(p.get("fb_name") or "")
        self._name_touched = True
        for combo, key in ((self.cytometer, "cytometer"),
                           (self.language, "language")):    # steps run before it keep the default
            if combo.findData(p.get(key)) >= 0:
                combo.setCurrentIndex(combo.findData(p.get(key)))
        cof = p.get("cofactor")
        self.cofactor.setText("" if cof is None else str(cof))
        self.test_mode.setChecked(bool(p.get("test_mode")))
        return warns

    def validate(self):
        d = self.fcs_dir.path()
        if not d or not Path(d).is_dir():
            return "Select an existing folder of FCS files."
        if not any(f.suffix.lower() == ".fcs" for f in Path(d).iterdir() if f.is_file()):
            return "The selected folder contains no .fcs file."
        if not self.fb_name.text().strip():
            return "Enter a name for the flowBunch."
        c = self.cofactor.text().strip()
        if c:
            try:
                if float(c.replace(",", ".")) <= 0:
                    return "The cofactor must be positive."
            except ValueError:
                pass                                   # text accepted: passed as is to fb_initiate
        return None

    def collect_parameters(self) -> dict:
        folder = Path(self.fcs_dir.path()).resolve()
        return {
            "fb_name": self.fb_name.text().strip(),
            "fcs_dir": str(folder),
            "cytometer": self.cytometer.currentData(),
            "language": self.language.currentData(),
            "cofactor": _number_or_text(self.cofactor.text()),
            "test_mode": self.test_mode.isChecked(),
        }
