from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any


_CREATE_SUSPENDED = 0x00000004
_INFINITE = 0xFFFFFFFF
_INVALID_RESUME = 0xFFFFFFFF
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_STARTF_USESTDHANDLES = 0x00000100
_STD_ERROR_HANDLE = -12
_STD_INPUT_HANDLE = -10
_STD_OUTPUT_HANDLE = -11


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(_StartupInfo),
        ctypes.POINTER(_ProcessInformation),
    ]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    return kernel


def _checked(value: Any, label: str) -> Any:
    if not value:
        raise OSError(ctypes.get_last_error(), label)
    return value


def _decode_specification(encoded: str) -> tuple[str, list[str], str]:
    if not encoded.isascii() or len(encoded) > 1_000_000:
        raise ValueError("invalid encoded specification")
    padding = "=" * (-len(encoded) % 4)
    payload = base64.urlsafe_b64decode(encoded + padding)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != {"executable", "args", "cwd"}:
        raise ValueError("invalid process specification")
    executable = value["executable"]
    arguments = value["args"]
    cwd = value["cwd"]
    if not isinstance(executable, str) or not executable or "\0" in executable:
        raise ValueError("invalid executable")
    if not isinstance(arguments, list) or len(arguments) > 10_000:
        raise ValueError("invalid argument list")
    if any(
        not isinstance(argument, str)
        or "\0" in argument
        or len(argument) > 100_000
        for argument in arguments
    ):
        raise ValueError("invalid process argument")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not Path(cwd).is_dir():
        raise ValueError("invalid working directory")
    resolved = executable if os.path.isabs(executable) else shutil.which(executable)
    if resolved is None or not Path(resolved).is_file():
        raise ValueError("executable is unavailable")
    return str(Path(resolved).resolve()), arguments, str(Path(cwd).resolve())


def _run_in_job(executable: str, arguments: list[str], cwd: str) -> int:
    kernel = _kernel32()
    job = _checked(kernel.CreateJobObjectW(None, None), "create job")
    process = _ProcessInformation()
    created = False
    try:
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _checked(
            kernel.SetInformationJobObject(
                job,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ),
            "configure job",
        )
        startup = _StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = _STARTF_USESTDHANDLES
        startup.hStdInput = kernel.GetStdHandle(_STD_INPUT_HANDLE)
        startup.hStdOutput = kernel.GetStdHandle(_STD_OUTPUT_HANDLE)
        startup.hStdError = kernel.GetStdHandle(_STD_ERROR_HANDLE)
        command = ctypes.create_unicode_buffer(
            subprocess.list2cmdline([executable, *arguments]),
        )
        _checked(
            kernel.CreateProcessW(
                executable,
                command,
                None,
                None,
                True,
                _CREATE_SUSPENDED,
                None,
                cwd,
                ctypes.byref(startup),
                ctypes.byref(process),
            ),
            "create process",
        )
        created = True
        _checked(
            kernel.AssignProcessToJobObject(job, process.hProcess),
            "assign process job",
        )
        if kernel.ResumeThread(process.hThread) == _INVALID_RESUME:
            raise OSError(ctypes.get_last_error(), "resume process")
        kernel.WaitForSingleObject(process.hProcess, _INFINITE)
        exit_code = wintypes.DWORD()
        _checked(
            kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)),
            "read process exit code",
        )
        return int(exit_code.value)
    except Exception:
        if created and process.hProcess:
            kernel.TerminateProcess(process.hProcess, 70)
        raise
    finally:
        if process.hThread:
            kernel.CloseHandle(process.hThread)
        if process.hProcess:
            kernel.CloseHandle(process.hProcess)
        kernel.CloseHandle(job)


def main() -> int:
    if sys.platform != "win32" or len(sys.argv) != 2:
        return 70
    try:
        executable, arguments, cwd = _decode_specification(sys.argv[1])
        return _run_in_job(executable, arguments, cwd)
    except Exception:
        sys.stderr.write("Windows job runner failed.\n")
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
