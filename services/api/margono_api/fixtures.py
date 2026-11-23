from datetime import UTC, datetime, timedelta
from random import Random
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

Workspace = Literal["web", "usb"]


class Fixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["SYNTHETIC"] = "SYNTHETIC"


class CaseFixture(Fixture):
    case_id: str
    label: str
    workspace: Workspace
    scenario: str
    reference_id: str
    created_at: AwareDatetime


class SourceProfile(Fixture):
    profile_id: str
    label: str
    behavior: Literal["fixture_available", "timeout_fixture"]


class DeviceProfile(Fixture):
    profile_id: str
    platform: Literal["Android", "iPhone"]
    capability: str
    result: Literal["sample_available", "unsupported"]


class Variation(Fixture):
    seed: int
    case_ids: tuple[str, ...]


class Catalog(Fixture):
    cases: tuple[CaseFixture, ...]
    sources: tuple[SourceProfile, ...]
    devices: tuple[DeviceProfile, ...]


FIXTURE_START = datetime(2026, 1, 1, tzinfo=UTC)

CATALOG = Catalog(
    sources=(
        SourceProfile(
            profile_id="SRC-FIXTURE",
            label="Feed simulasi",
            behavior="fixture_available",
        ),
        SourceProfile(
            profile_id="SRC-TIMEOUT", label="Sumber timeout", behavior="timeout_fixture"
        ),
    ),
    devices=(
        DeviceProfile(
            profile_id="DEV-ANDROID",
            platform="Android",
            capability="Metadata keamanan sintetis",
            result="sample_available",
        ),
        DeviceProfile(
            profile_id="DEV-IPHONE",
            platform="iPhone",
            capability="Diagnostik indikator ancaman",
            result="unsupported",
        ),
    ),
    cases=tuple(
        CaseFixture(
            case_id=f"SYN-{number:03d}",
            label=label,
            workspace=workspace,
            scenario=scenario,
            reference_id=reference_id,
            created_at=FIXTURE_START + timedelta(minutes=number - 1),
        )
        for number, (label, workspace, scenario, reference_id) in enumerate(
            (
                (
                    "Indikator domain",
                    "web",
                    "Domain contoh margono.test",
                    "SRC-FIXTURE",
                ),
                ("Label kasus ganda", "web", "Baris referensi pertama", "SRC-FIXTURE"),
                ("Label kasus ganda", "web", "Baris referensi kedua", "SRC-FIXTURE"),
                (
                    "Impor spreadsheet",
                    "web",
                    "Sel yang menyerupai formula",
                    "SRC-FIXTURE",
                ),
                ("Impor CSV", "web", "Baris tanpa label referensi", "SRC-FIXTURE"),
                ("Ketersediaan sumber", "web", "Timeout sumber tiruan", "SRC-TIMEOUT"),
                ("Antrean offline", "web", "Antrean dimulai ulang", "SRC-FIXTURE"),
                ("Pembatalan job", "web", "Pembatalan selama proses", "SRC-FIXTURE"),
                ("Review indikator", "web", "Temuan tidak konklusif", "SRC-FIXTURE"),
                ("Review indikator", "web", "Temuan positif palsu", "SRC-FIXTURE"),
                (
                    "Diagnostik Android",
                    "usb",
                    "Metadata contoh tersedia",
                    "DEV-ANDROID",
                ),
                (
                    "Diagnostik iPhone",
                    "usb",
                    "Kapabilitas tidak didukung",
                    "DEV-IPHONE",
                ),
                (
                    "Persetujuan ditolak",
                    "usb",
                    "Pemilik menolak persetujuan",
                    "DEV-ANDROID",
                ),
                (
                    "Persetujuan dicabut",
                    "usb",
                    "Persetujuan dicabut saat antre",
                    "DEV-ANDROID",
                ),
                (
                    "Sesi USB terputus",
                    "usb",
                    "Sambungan tiruan terputus",
                    "DEV-ANDROID",
                ),
                ("Integritas bukti", "web", "Hash bukti tidak cocok", "SRC-FIXTURE"),
                (
                    "Integritas manifest",
                    "web",
                    "Manifest contoh berubah",
                    "SRC-FIXTURE",
                ),
                (
                    "Replay sinkronisasi",
                    "usb",
                    "Event sinkronisasi ganda",
                    "DEV-ANDROID",
                ),
                (
                    "Konflik sinkronisasi",
                    "usb",
                    "Versi bukti bertentangan",
                    "DEV-ANDROID",
                ),
                (
                    "Pemulihan bukti",
                    "web",
                    "Pemulihan memerlukan review",
                    "SRC-FIXTURE",
                ),
            ),
            start=1,
        )
    ),
)


def generate_variation(seed: int) -> Variation:
    """Sample three fixed cases per workspace for a repeatable smoke-test plan."""
    random = Random(seed)
    web_ids = [case.case_id for case in CATALOG.cases if case.workspace == "web"]
    usb_ids = [case.case_id for case in CATALOG.cases if case.workspace == "usb"]
    return Variation(
        seed=seed, case_ids=tuple(random.sample(web_ids, 3) + random.sample(usb_ids, 3))
    )
