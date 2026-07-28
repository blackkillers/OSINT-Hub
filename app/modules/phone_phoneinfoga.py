"""OSINT-Hub — PhoneInfoga Phone Module (Real Implementation)"""

import json
import time
from uuid import UUID
from typing import List

import structlog

from app.modules.base import BaseOSINTModule
from app.worker import execute_cli_command
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)


class PhoneInfogaModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "phone_phoneinfoga"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.PHONE]

    async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
        start = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        root_id = f"phone:{target}"
        nodes: List[NodeModel] = [
            NodeModel(id=root_id, label=target, type=NodeTypeEnum.PHONE,
                      metadata={"is_target": True})
        ]
        edges: List[EdgeModel] = []
        raw: dict = {}

        try:
            # Try JSON output first
            cmd = ["phoneinfoga", "scan", "-n", target]
            exit_code, stdout, stderr = await execute_cli_command(cmd, timeout_seconds=60)

            raw = {"stdout": stdout[:3000], "stderr": stderr[:1000]}

            # Parse country/carrier/line type from output
            for line in stdout.splitlines():
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip().lower()
                    val = val.strip()
                    if val and key in ("country", "local", "international", "carrier",
                                       "line type", "location"):
                        node_id = f"phone_info:{key.replace(' ', '_')}:{val[:30]}"
                        nodes.append(NodeModel(
                            id=node_id, label=f"{key.title()}: {val}",
                            type=NodeTypeEnum.OTHER,
                            metadata={"field": key, "value": val}
                        ))
                        edges.append(EdgeModel(
                            source=root_id, target=node_id,
                            relation=key.upper().replace(" ", "_"), confidence=0.95
                        ))

            # Also extract number info via phonenumbers library
            try:
                import phonenumbers
                from phonenumbers import geocoder, carrier, timezone as pn_tz
                parsed = phonenumbers.parse(target, None)
                if phonenumbers.is_valid_number(parsed):
                    country = geocoder.description_for_number(parsed, "en")
                    operator = carrier.name_for_number(parsed, "en")
                    tz = pn_tz.time_zones_for_number(parsed)

                    if country:
                        loc_id = f"location:{country.lower().replace(' ', '_')}"
                        nodes.append(NodeModel(
                            id=loc_id, label=country,
                            type=NodeTypeEnum.LOCATION,
                            metadata={"type": "country"}
                        ))
                        edges.append(EdgeModel(
                            source=root_id, target=loc_id,
                            relation="LOCATED_IN", confidence=0.95
                        ))

                    if operator:
                        carrier_id = f"carrier:{operator.lower().replace(' ', '_')}"
                        nodes.append(NodeModel(
                            id=carrier_id, label=operator,
                            type=NodeTypeEnum.OTHER,
                            metadata={"type": "carrier"}
                        ))
                        edges.append(EdgeModel(
                            source=root_id, target=carrier_id,
                            relation="USES_CARRIER", confidence=0.9
                        ))

                    raw["parsed"] = {
                        "country": country,
                        "carrier": operator,
                        "timezones": list(tz),
                        "national_number": str(parsed.national_number),
                        "country_code": parsed.country_code,
                        "valid": True,
                    }
            except Exception:
                pass

            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name,
                status=StatusEnum.SUCCESS if nodes else StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges, raw_data=raw
            )

        except FileNotFoundError:
            # Fallback: use only phonenumbers library
            try:
                import phonenumbers
                from phonenumbers import geocoder, carrier
                parsed = phonenumbers.parse(target, None)
                if phonenumbers.is_valid_number(parsed):
                    country = geocoder.description_for_number(parsed, "en")
                    operator = carrier.name_for_number(parsed, "en")
                    if country:
                        loc_id = f"location:{country.lower().replace(' ', '_')}"
                        nodes.append(NodeModel(id=loc_id, label=country, type=NodeTypeEnum.LOCATION, metadata={}))
                        edges.append(EdgeModel(source=root_id, target=loc_id, relation="LOCATED_IN", confidence=0.9))
                    if operator:
                        car_id = f"carrier:{operator.lower()}"
                        nodes.append(NodeModel(id=car_id, label=operator, type=NodeTypeEnum.OTHER, metadata={}))
                        edges.append(EdgeModel(source=root_id, target=car_id, relation="USES_CARRIER", confidence=0.9))
            except Exception:
                pass

            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges,
                error="phoneinfoga binary not found — basic lookup only via phonenumbers"
            )
        except Exception as exc:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.FAILED,
                execution_time_ms=int((time.time() - start) * 1000),
                error=str(exc)
            )
