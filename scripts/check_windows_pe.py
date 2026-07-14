"""Validate Vista compatible PE headers in a PyInstaller x86 release."""

import io
import struct
import sys

import pefile
from PyInstaller.archive.readers import CArchiveReader


IMAGE_FILE_MACHINE_I386 = 0x014C
PE32_MAGIC = 0x010B
WINDOWS_GUI_SUBSYSTEM = 2
WINDOWS_VISTA_VERSION = (6, 0)
VISTA_SUPPORTED_OS_GUID = b"{e2011457-1546-43c5-a5fe-008deee3d3f0}"

# These are the complete x86 files from the fixed Python 3.7.9 Universal CRT
# package. Microsoft supplies them for local use on older Windows systems.
# Some of these DLLs use 10.0 PE header values, so the header version limit is
# not applied to this exact set. Their architecture and imports are still checked.
APP_LOCAL_UCRT_DLLS = {
    b"API-MS-WIN-CORE-CONSOLE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-DATETIME-L1-1-0.DLL",
    b"API-MS-WIN-CORE-DEBUG-L1-1-0.DLL",
    b"API-MS-WIN-CORE-ERRORHANDLING-L1-1-0.DLL",
    b"API-MS-WIN-CORE-FILE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-FILE-L1-2-0.DLL",
    b"API-MS-WIN-CORE-FILE-L2-1-0.DLL",
    b"API-MS-WIN-CORE-HANDLE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-HEAP-L1-1-0.DLL",
    b"API-MS-WIN-CORE-INTERLOCKED-L1-1-0.DLL",
    b"API-MS-WIN-CORE-LIBRARYLOADER-L1-1-0.DLL",
    b"API-MS-WIN-CORE-LOCALIZATION-L1-2-0.DLL",
    b"API-MS-WIN-CORE-MEMORY-L1-1-0.DLL",
    b"API-MS-WIN-CORE-NAMEDPIPE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-PROCESSENVIRONMENT-L1-1-0.DLL",
    b"API-MS-WIN-CORE-PROCESSTHREADS-L1-1-0.DLL",
    b"API-MS-WIN-CORE-PROCESSTHREADS-L1-1-1.DLL",
    b"API-MS-WIN-CORE-PROFILE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-RTLSUPPORT-L1-1-0.DLL",
    b"API-MS-WIN-CORE-STRING-L1-1-0.DLL",
    b"API-MS-WIN-CORE-SYNCH-L1-1-0.DLL",
    b"API-MS-WIN-CORE-SYNCH-L1-2-0.DLL",
    b"API-MS-WIN-CORE-SYSINFO-L1-1-0.DLL",
    b"API-MS-WIN-CORE-TIMEZONE-L1-1-0.DLL",
    b"API-MS-WIN-CORE-UTIL-L1-1-0.DLL",
    b"API-MS-WIN-CRT-CONIO-L1-1-0.DLL",
    b"API-MS-WIN-CRT-CONVERT-L1-1-0.DLL",
    b"API-MS-WIN-CRT-ENVIRONMENT-L1-1-0.DLL",
    b"API-MS-WIN-CRT-FILESYSTEM-L1-1-0.DLL",
    b"API-MS-WIN-CRT-HEAP-L1-1-0.DLL",
    b"API-MS-WIN-CRT-LOCALE-L1-1-0.DLL",
    b"API-MS-WIN-CRT-MATH-L1-1-0.DLL",
    b"API-MS-WIN-CRT-MULTIBYTE-L1-1-0.DLL",
    b"API-MS-WIN-CRT-PRIVATE-L1-1-0.DLL",
    b"API-MS-WIN-CRT-PROCESS-L1-1-0.DLL",
    b"API-MS-WIN-CRT-RUNTIME-L1-1-0.DLL",
    b"API-MS-WIN-CRT-STDIO-L1-1-0.DLL",
    b"API-MS-WIN-CRT-STRING-L1-1-0.DLL",
    b"API-MS-WIN-CRT-TIME-L1-1-0.DLL",
    b"API-MS-WIN-CRT-UTILITY-L1-1-0.DLL",
    b"UCRTBASE.DLL",
}

# These imports are not available on Vista. Check them in addition to the PE
# version headers and the fixed build tool versions.
KNOWN_POST_VISTA_IMPORTS = {
    b"KERNEL32.DLL": {
        b"ADDDLLDIRECTORY",
        b"CREATEFILE2",
        b"GETACTIVEPROCESSORCOUNT",
        b"GETACTIVEPROCESSORGROUPCOUNT",
        b"GETCURRENTPACKAGEFULLNAME",
        b"GETCURRENTPROCESSORNUMBEREX",
        b"GETCURRENTTHREADSTACKLIMITS",
        b"GETMAXIMUMPROCESSORCOUNT",
        b"GETMAXIMUMPROCESSORGROUPCOUNT",
        b"GETOVERLAPPEDRESULTEX",
        b"GETPACKAGEFAMILYNAME",
        b"GETPACKAGEPATHBYFULLNAME",
        b"GETPROCESSINFORMATION",
        b"GETSYSTEMTIMEPRECISEASFILETIME",
        b"GETTEMPPATH2A",
        b"GETTEMPPATH2W",
        b"GETTHREADINFORMATION",
        b"ISWOW64PROCESS2",
        b"K32ENUMPROCESSMODULES",
        b"K32GETMODULEFILENAMEEXA",
        b"K32GETMODULEFILENAMEEXW",
        b"PREFETCHVIRTUALMEMORY",
        b"REMOVEDLLDIRECTORY",
        b"SETDEFAULTDLLDIRECTORIES",
        b"SETPROCESSINFORMATION",
        b"SETTHREADDESCRIPTION",
        b"SETTHREADINFORMATION",
        b"WAITONADDRESS",
        b"WAKEBYADDRESSALL",
        b"WAKEBYADDRESSSINGLE",
    },
}
KNOWN_POST_VISTA_DLLS = {
    b"API-MS-WIN-CORE-PATH-L1-1-0.DLL",
    b"COMBASE.DLL",
    b"KERNELBASE.DLL",
    b"SHCORE.DLL",
}


def _read_exact(handle, size, description):
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated {}".format(description))
    return data


def inspect_pe(source):
    if isinstance(source, bytes):
        handle = io.BytesIO(source)
        close_handle = True
    else:
        handle = open(source, "rb")
        close_handle = True

    try:
        dos_header = _read_exact(handle, 64, "DOS header")
        if dos_header[:2] != b"MZ":
            raise ValueError("missing DOS MZ signature")

        pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
        handle.seek(pe_offset)
        if _read_exact(handle, 4, "PE signature") != b"PE\0\0":
            raise ValueError("missing PE signature")

        coff_header = _read_exact(handle, 20, "COFF header")
        machine = struct.unpack_from("<H", coff_header, 0)[0]
        optional_header_size = struct.unpack_from("<H", coff_header, 16)[0]
        optional_header = _read_exact(handle, optional_header_size, "optional header")
    finally:
        if close_handle:
            handle.close()

    if len(optional_header) < 70:
        raise ValueError("optional header is too small")

    magic = struct.unpack_from("<H", optional_header, 0)[0]
    os_version = struct.unpack_from("<HH", optional_header, 40)
    subsystem_version = struct.unpack_from("<HH", optional_header, 48)
    subsystem = struct.unpack_from("<H", optional_header, 68)[0]

    return machine, magic, os_version, subsystem_version, subsystem


def inspect_imports(data):
    image = pefile.PE(data=data, fast_load=True)
    try:
        image.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ]
        )
        imported_dlls = set()
        found = []
        for directory_name in (
            "DIRECTORY_ENTRY_IMPORT",
            "DIRECTORY_ENTRY_DELAY_IMPORT",
        ):
            for imported_dll in getattr(image, directory_name, []):
                dll_name = imported_dll.dll.upper()
                imported_dlls.add(dll_name)
                if dll_name in KNOWN_POST_VISTA_DLLS or dll_name.startswith(b"EXT-MS-"):
                    found.append(dll_name.decode("ascii", "replace"))

                forbidden_names = KNOWN_POST_VISTA_IMPORTS.get(dll_name, set())
                for imported_symbol in imported_dll.imports:
                    if (
                        imported_symbol.name
                        and imported_symbol.name.upper() in forbidden_names
                    ):
                        found.append(
                            "{}!{}".format(
                                dll_name.decode("ascii", "replace"),
                                imported_symbol.name.decode("ascii", "replace"),
                            )
                        )
        return imported_dlls, sorted(set(found))
    finally:
        image.close()


def manifest_declares_vista(data):
    image = pefile.PE(data=data, fast_load=True)
    try:
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        resource_root = getattr(image, "DIRECTORY_ENTRY_RESOURCE", None)
        if resource_root is None:
            return False

        for type_entry in resource_root.entries:
            if type_entry.id != pefile.RESOURCE_TYPE["RT_MANIFEST"]:
                continue
            for name_entry in type_entry.directory.entries:
                for language_entry in name_entry.directory.entries:
                    resource = language_entry.data.struct
                    manifest = image.get_data(resource.OffsetToData, resource.Size)
                    if VISTA_SUPPORTED_OS_GUID in manifest.lower():
                        return True
        return False
    finally:
        image.close()


def windows_basename(name):
    return name.replace("\\", "/").rsplit("/", 1)[-1].encode("ascii", "replace").upper()


def format_dll_names(names):
    return ", ".join(name.decode("ascii", "replace") for name in sorted(names))


def validate_pe(data, description, require_gui=False, allow_newer_headers=False):
    machine, magic, os_version, subsystem_version, subsystem = inspect_pe(data)

    if machine != IMAGE_FILE_MACHINE_I386:
        raise ValueError(
            "{}: expected i386 machine 0x{:04x}, found 0x{:04x}".format(
                description, IMAGE_FILE_MACHINE_I386, machine
            )
        )
    if magic != PE32_MAGIC:
        raise ValueError(
            "{}: expected PE32 optional header 0x{:04x}, found 0x{:04x}".format(
                description, PE32_MAGIC, magic
            )
        )
    if not allow_newer_headers and os_version > WINDOWS_VISTA_VERSION:
        raise ValueError(
            "{}: minimum OS header {}.{} is newer than Vista 6.0".format(
                description, *os_version
            )
        )
    if not allow_newer_headers and subsystem_version > WINDOWS_VISTA_VERSION:
        raise ValueError(
            "{}: minimum subsystem {}.{} is newer than Vista 6.0".format(
                description, *subsystem_version
            )
        )
    if require_gui and subsystem != WINDOWS_GUI_SUBSYSTEM:
        raise ValueError(
            "{}: expected Windows GUI subsystem {}, found {}".format(
                description, WINDOWS_GUI_SUBSYSTEM, subsystem
            )
        )

    imported_dlls, post_vista_imports = inspect_imports(data)
    if post_vista_imports:
        raise ValueError(
            "{}: imports APIs that are not available on Vista: {}".format(
                description, ", ".join(post_vista_imports)
            )
        )

    return os_version, subsystem_version, imported_dlls


def main(argv):
    if len(argv) != 2:
        print("usage: check_windows_pe.py <executable>", file=sys.stderr)
        return 2

    path = argv[1]
    try:
        with open(path, "rb") as handle:
            executable_data = handle.read()
        os_version, subsystem_version, imported_dlls = validate_pe(
            executable_data, path, require_gui=True
        )
        if not manifest_declares_vista(executable_data):
            raise ValueError("the executable manifest does not declare Windows Vista support")

        archive = CArchiveReader(path)
        embedded_pe_count = 0
        embedded_dlls = set()
        all_imported_dlls = set(imported_dlls)
        for name, entry in archive.toc.items():
            if entry[-1] != "b":
                continue
            data = archive.extract(name)
            if not data.startswith(b"MZ"):
                continue
            basename = windows_basename(name)
            embedded_dlls.add(basename)
            _, _, native_imports = validate_pe(
                data,
                "embedded {}".format(name),
                allow_newer_headers=basename in APP_LOCAL_UCRT_DLLS,
            )
            all_imported_dlls.update(native_imports)
            embedded_pe_count += 1

        if not embedded_pe_count:
            raise ValueError("the PyInstaller archive contains no native libraries")

        missing_ucrt_dlls = APP_LOCAL_UCRT_DLLS - embedded_dlls
        if missing_ucrt_dlls:
            raise ValueError(
                "the local x86 Universal CRT set is incomplete: {}".format(
                    format_dll_names(missing_ucrt_dlls)
                )
            )

        imported_api_dlls = {
            name
            for name in all_imported_dlls
            if name.startswith(b"API-MS-")
        }
        unsupported_api_dlls = imported_api_dlls - APP_LOCAL_UCRT_DLLS
        if unsupported_api_dlls:
            raise ValueError(
                "imports API DLLs outside the Vista runtime set: {}".format(
                    format_dll_names(unsupported_api_dlls)
                )
            )

        missing_imported_dlls = imported_api_dlls - embedded_dlls
        if missing_imported_dlls:
            raise ValueError(
                "does not include imported API DLLs: {}".format(
                    format_dll_names(missing_imported_dlls)
                )
            )
    except (OSError, ValueError, struct.error, pefile.PEFormatError) as error:
        print("Windows compatibility check failed: {}: {}".format(path, error), file=sys.stderr)
        return 1

    print(
        "Verified {}: PE32/i386, Windows GUI, OS {}.{}, subsystem {}.{}, "
        "and {} embedded PE32/i386 native files with the complete fixed x86 "
        "Universal CRT set and no known imports that require a later Windows version".format(
            path,
            os_version[0],
            os_version[1],
            subsystem_version[0],
            subsystem_version[1],
            embedded_pe_count,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
