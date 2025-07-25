from typing import Union, Iterator
from pathlib import Path

from capa.features.insn import API, Number
from capa.features.common import (
    OS,
    ARCH_ARM,
    ARCH_I386,
    ARCH_AMD64,
    FORMAT_APK,
    OS_ANDROID,
    ARCH_AARCH64,
    Arch,
    Format,
    String,
    Feature,
)
from capa.features.address import NO_ADDRESS, Address, ThreadAddress, ProcessAddress, DynamicCallAddress, _NoAddress
from capa.features.extractors.frida.models import Call, FridaReport
from capa.features.extractors.base_extractor import (
    CallHandle,
    SampleHashes,
    ThreadHandle,
    ProcessHandle,
    DynamicFeatureExtractor,
)


class FridaExtractor(DynamicFeatureExtractor):
    """
    Frida dynamic analysis feature extractor for Android applications.

    Processes JSON output from Frida instrumentation to extract behavioral features.
    """

    def __init__(self, report: FridaReport):
        # TODO: From what I’ve found, Frida cannot access original APK file to compute hashes at runtime.
        # we may need to require users to provide both the Frida-generated log file and original file to capa,
        # like we do with other extractors e.g. BinExport, VMRay, etc..
        super().__init__(hashes=SampleHashes(md5="", sha1="", sha256=""))
        self.report: FridaReport = report

    def get_base_address(self) -> Union[_NoAddress, None]:
        return NO_ADDRESS

    def extract_global_features(self) -> Iterator[tuple[Feature, Address]]:
        """Basic global features"""
        yield OS(OS_ANDROID), NO_ADDRESS

        if self.report.processes:
            process = self.report.processes[0]

            if process.arch:
                arch_mapping = {"arm64": ARCH_AARCH64, "arm": ARCH_ARM, "x64": ARCH_AMD64, "ia32": ARCH_I386}
                capa_arch = arch_mapping.get(process.arch, process.arch)
                yield Arch(capa_arch), NO_ADDRESS

        yield Format(FORMAT_APK), NO_ADDRESS

    def extract_file_features(self) -> Iterator[tuple[Feature, Address]]:
        """Basic file features"""
        yield String(self.report.package_name), NO_ADDRESS

    def get_processes(self) -> Iterator[ProcessHandle]:
        """Get all processes from the report"""
        for process in self.report.processes:
            addr = ProcessAddress(pid=process.pid, ppid=0)
            yield ProcessHandle(address=addr, inner=process)

    def extract_process_features(self, ph: ProcessHandle) -> Iterator[tuple[Feature, Address]]:
        # TODO: we have not identified process-specific features for Frida yet
        yield from []

    def get_process_name(self, ph: ProcessHandle) -> str:
        return ph.inner.package_name

    def get_threads(self, ph: ProcessHandle) -> Iterator[ThreadHandle]:
        """Get all threads by grouping calls by thread_id"""
        thread_ids = set()
        for call in ph.inner.calls:
            thread_ids.add(call.thread_id)

        for tid in thread_ids:
            addr = ThreadAddress(process=ph.address, tid=tid)
            yield ThreadHandle(address=addr, inner={"tid": tid})

    def extract_thread_features(self, ph: ProcessHandle, th: ThreadHandle) -> Iterator[tuple[Feature, Address]]:
        # TODO: we have not identified thread-specific features for Frida yet
        yield from []

    def get_calls(self, ph: ProcessHandle, th: ThreadHandle) -> Iterator[CallHandle]:
        """Get all API calls in a specific thread"""
        for call in ph.inner.calls:
            if call.thread_id == th.address.tid:
                addr = DynamicCallAddress(thread=th.address, id=call.call_id)
                yield CallHandle(address=addr, inner=call)

    def extract_call_features(
        self, ph: ProcessHandle, th: ThreadHandle, ch: CallHandle
    ) -> Iterator[tuple[Feature, Address]]:
        """Extract features from individual API calls"""
        call: Call = ch.inner

        yield API(call.api_name), ch.address

        if call.arguments:
            for arg_obj in call.arguments:
                arg_value = arg_obj.value
                if isinstance(arg_value, (int, float, bool)):
                    yield Number(arg_value), ch.address
                elif isinstance(arg_value, str):
                    yield String(arg_value), ch.address

    def get_call_name(self, ph: ProcessHandle, th: ThreadHandle, ch: CallHandle) -> str:
        """Format API call name and parameters"""
        call: Call = ch.inner

        parts = []
        parts.append(call.api_name)
        parts.append("(")

        if call.arguments:
            args_display = []
            for arg_obj in call.arguments:
                display_value = str(arg_obj.value)
                # Current implementation: Display name=value, since we have arg name
                args_display.append(f"{arg_obj.name}={display_value}")
            parts.append(", ".join(args_display))

        parts.append(")")

        return "".join(parts)

    @classmethod
    def from_jsonl_file(cls, jsonl_path: Path) -> "FridaExtractor":
        """Entry point: Create an extractor from a JSONL file"""
        report = FridaReport.from_jsonl_file(jsonl_path)
        return cls(report)
