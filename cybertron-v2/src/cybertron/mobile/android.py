"""Android APK Static Analysis"""
import zipfile
from pathlib import Path
from typing import Dict, List
import structlog
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class AndroidAnalyzer(PluginInterface):
    name = "android_analyzer"
    version = "2.0.0"
    description = "Static analysis of Android APK files"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        findings = []
        apk_path = Path(target)

        if not apk_path.exists() or apk_path.suffix != ".apk":
            return TaskResult(
                task_id=__import__("uuid").uuid4().hex,
                status=TaskStatus.FAILED,
                error="Invalid APK file"
            )

        with zipfile.ZipFile(apk_path, "r") as zf:
            if "AndroidManifest.xml" in zf.namelist():
                manifest_data = zf.read("AndroidManifest.xml")
                try:
                    from androguard.core.axml import AXMLPrinter
                    import xml.etree.ElementTree as ET
                    axml = AXMLPrinter(manifest_data)
                    xml_str = axml.get_buff()
                    root = ET.fromstring(xml_str)

                    app_elem = root.find(".//application")
                    if app_elem is not None:
                        ns = "{http://schemas.android.com/apk/res/android}"
                        if app_elem.get(f"{ns}debuggable") == "true":
                            findings.append(Finding(
                                title="Debuggable Application",
                                description="APK has android:debuggable=true",
                                severity=Severity.HIGH,
                                category="mobile",
                                target=str(apk_path),
                                remediation="Remove debuggable flag"
                            ))
                        if app_elem.get(f"{ns}allowBackup") == "true":
                            findings.append(Finding(
                                title="AllowBackup Enabled",
                                description="Application data can be backed up via adb",
                                severity=Severity.MEDIUM,
                                category="mobile",
                                target=str(apk_path)
                            ))
                except Exception as e:
                    logger.warning("manifest_parse_failed", error=str(e))

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )
