"""Binary Analysis Engine"""
import struct
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger()


class BinaryFormat(Enum):
    PE = "pe"
    ELF = "elf"
    MACH_O = "macho"
    RAW = "raw"
    UNKNOWN = "unknown"


class Architecture(Enum):
    X86 = "x86"
    X64 = "x64"
    ARM = "arm"
    ARM64 = "arm64"
    MIPS = "mips"
    PPC = "ppc"
    RISCV = "riscv"


@dataclass
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_address: int
    raw_size: int
    permissions: str
    entropy: float = 0.0
    md5: str = ""


@dataclass
class Import:
    dll: str
    name: str
    address: int


@dataclass
class Export:
    name: str
    address: int
    ordinal: Optional[int] = None


@dataclass
class BinaryInfo:
    path: Path
    format: BinaryFormat
    arch: Architecture
    bitness: int
    entry_point: int
    image_base: int
    sections: List[Section] = field(default_factory=list)
    imports: List[Import] = field(default_factory=list)
    exports: List[Export] = field(default_factory=list)
    strings: List[str] = field(default_factory=list)
    suspicious_patterns: List[Dict] = field(default_factory=list)
    hashes: Dict[str, str] = field(default_factory=dict)
    packer: Optional[str] = None


class BinaryAnalyzer:
    def __init__(self, max_size_mb: int = 500):
        self.max_size = max_size_mb * 1024 * 1024
        self.logger = structlog.get_logger(analyzer="binary")

    def analyze(self, path: Path) -> BinaryInfo:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Binary not found: {path}")
        if path.stat().st_size > self.max_size:
            raise ValueError(f"Binary exceeds max size")

        data = path.read_bytes()
        fmt = self._detect_format(data)

        if fmt == BinaryFormat.PE:
            return self._parse_pe(path, data)
        elif fmt == BinaryFormat.ELF:
            return self._parse_elf(path, data)
        elif fmt == BinaryFormat.MACH_O:
            return self._parse_macho(path, data)
        else:
            return self._parse_raw(path, data)

    def _detect_format(self, data: bytes) -> BinaryFormat:
        if data[:2] == b"MZ":
            return BinaryFormat.PE
        elif data[:4] == b"\x7fELF":
            return BinaryFormat.ELF
        elif data[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            return BinaryFormat.MACH_O
        return BinaryFormat.RAW

    def _parse_pe(self, path, data):
        import pefile
        pe = pefile.PE(data=data)
        arch = Architecture.X86
        bitness = 32
        if pe.FILE_HEADER.Machine == pefile.MACHINE_TYPE.get("IMAGE_FILE_MACHINE_AMD64", 0x8664):
            arch = Architecture.X64
            bitness = 64

        info = BinaryInfo(
            path=path, format=BinaryFormat.PE, arch=arch, bitness=bitness,
            entry_point=pe.OPTIONAL_HEADER.AddressOfEntryPoint + pe.OPTIONAL_HEADER.ImageBase,
            image_base=pe.OPTIONAL_HEADER.ImageBase,
            hashes=self._compute_hashes(data)
        )

        for section in pe.sections:
            name = section.Name.decode("utf-8", errors="ignore").strip("\x00")
            sec = Section(
                name=name,
                virtual_address=section.VirtualAddress + pe.OPTIONAL_HEADER.ImageBase,
                virtual_size=section.Misc_VirtualSize,
                raw_address=section.PointerToRawData,
                raw_size=section.SizeOfRawData,
                permissions=self._pe_permissions(section.Characteristics),
                entropy=section.get_entropy(),
                md5=hashlib.md5(section.get_data()).hexdigest()
            )
            info.sections.append(sec)
            if sec.entropy > 7.5:
                info.suspicious_patterns.append({
                    "type": "high_entropy", "section": name, "entropy": sec.entropy
                })

        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dll = entry.dll.decode("utf-8", errors="ignore")
                for imp in entry.imports:
                    info.imports.append(Import(
                        dll=dll,
                        name=imp.name.decode("utf-8", errors="ignore") if imp.name else f"ord_{imp.ordinal}",
                        address=imp.address
                    ))

        info.strings = self._extract_strings(data)
        info.packer = self._detect_packer_pe(pe)
        return info

    def _parse_elf(self, path, data):
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import SymbolTableSection

        elf = ELFFile(data)
        arch_map = {
            "EM_X86_64": (Architecture.X64, 64),
            "EM_386": (Architecture.X86, 32),
            "EM_ARM": (Architecture.ARM, 32),
            "EM_AARCH64": (Architecture.ARM64, 64),
        }
        arch, bitness = arch_map.get(elf.header["e_machine"], (Architecture.X86, 32))

        info = BinaryInfo(
            path=path, format=BinaryFormat.ELF, arch=arch, bitness=bitness,
            entry_point=elf.header["e_entry"], image_base=0x400000,
            hashes=self._compute_hashes(data)
        )

        for section in elf.iter_sections():
            sec = Section(
                name=section.name,
                virtual_address=section["sh_addr"],
                virtual_size=section["sh_size"],
                raw_address=section["sh_offset"],
                raw_size=section["sh_size"],
                permissions=self._elf_permissions(section["sh_flags"]),
                entropy=self._calculate_entropy(section.data()),
                md5=hashlib.md5(section.data()).hexdigest()
            )
            info.sections.append(sec)

        info.strings = self._extract_strings(data)
        return info

    def _parse_macho(self, path, data):
        info = BinaryInfo(
            path=path, format=BinaryFormat.MACH_O, arch=Architecture.X64,
            bitness=64, entry_point=0, image_base=0x100000000,
            hashes=self._compute_hashes(data), strings=self._extract_strings(data)
        )
        return info

    def _parse_raw(self, path, data):
        return BinaryInfo(
            path=path, format=BinaryFormat.RAW, arch=Architecture.X86,
            bitness=32, entry_point=0, image_base=0,
            hashes=self._compute_hashes(data), strings=self._extract_strings(data)
        )

    def _compute_hashes(self, data):
        return {
            "md5": hashlib.md5(data).hexdigest(),
            "sha1": hashlib.sha1(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def _calculate_entropy(self, data):
        if not data:
            return 0.0
        from math import log2
        counts = [0] * 256
        for byte in data:
            counts[byte] += 1
        entropy = 0.0
        length = len(data)
        for count in counts:
            if count == 0:
                continue
            p = count / length
            entropy -= p * log2(p)
        return entropy

    def _extract_strings(self, data, min_length=4):
        import re
        ascii_strings = re.findall(rb"[\x20-\x7e]{%d,}" % min_length, data)
        return [s.decode("ascii", errors="ignore") for s in ascii_strings]

    def _pe_permissions(self, characteristics):
        perms = ""
        if characteristics & 0x40000000: perms += "r"
        if characteristics & 0x80000000: perms += "w"
        if characteristics & 0x20000000: perms += "x"
        return perms or "r"

    def _elf_permissions(self, flags):
        perms = ""
        if flags & 0x4: perms += "r"
        if flags & 0x2: perms += "w"
        if flags & 0x1: perms += "x"
        return perms or "r"

    def _detect_packer_pe(self, pe):
        packers = {b"UPX": "UPX", b"ASPack": "ASPack", b" Themida ": "Themida", b"VMProtect": "VMProtect"}
        data = bytes(pe.__data__)
        for sig, name in packers.items():
            if sig in data:
                return name
        return None
