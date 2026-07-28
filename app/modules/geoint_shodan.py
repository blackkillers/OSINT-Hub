"""OSINT-Hub — Shodan Geo/IP Module (Real Implementation — API key optional)"""

import json
import os
import time
from uuid import UUID
from typing import List

import httpx
import structlog

from app.modules.base import BaseOSINTModule
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)

SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "")


class ShodanModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "geoint_shodan"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.IP, TargetTypeEnum.DOMAIN]

    async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
        start = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        root_id = f"ip:{target}" if target_type == TargetTypeEnum.IP else f"domain:{target}"
        nodes: List[NodeModel] = [
            NodeModel(id=root_id, label=target,
                      type=NodeTypeEnum.IP if target_type == TargetTypeEnum.IP else NodeTypeEnum.DOMAIN,
                      metadata={"is_target": True})
        ]
        edges: List[EdgeModel] = []
        raw: dict = {}

        # ─── Shodan API (if key available) ───────────────────────────────────
        if SHODAN_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    # Resolve domain to IP first if needed
                    ip = target
                    if target_type == TargetTypeEnum.DOMAIN:
                        dns_resp = await client.get(
                            f"https://api.shodan.io/dns/resolve?hostnames={target}&key={SHODAN_API_KEY}"
                        )
                        dns_data = dns_resp.json()
                        ip = dns_data.get(target, target)

                    resp = await client.get(
                        f"https://api.shodan.io/shodan/host/{ip}?key={SHODAN_API_KEY}"
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        raw = data

                        # Country / City
                        country = data.get("country_name", "")
                        city = data.get("city", "")
                        org = data.get("org", "")
                        isp = data.get("isp", "")
                        os_info = data.get("os", "")

                        if country:
                            loc_id = f"location:{country.lower().replace(' ', '_')}"
                            nodes.append(NodeModel(id=loc_id, label=f"{city}, {country}" if city else country,
                                                   type=NodeTypeEnum.LOCATION, metadata={"country": country, "city": city}))
                            edges.append(EdgeModel(source=root_id, target=loc_id, relation="LOCATED_IN", confidence=0.95))

                        if org:
                            org_id = f"org:{org.lower().replace(' ', '_')[:30]}"
                            nodes.append(NodeModel(id=org_id, label=org, type=NodeTypeEnum.OTHER,
                                                   metadata={"type": "organization"}))
                            edges.append(EdgeModel(source=root_id, target=org_id, relation="BELONGS_TO_ORG", confidence=0.9))

                        # Open ports
                        for port_info in data.get("data", [])[:10]:
                            port = port_info.get("port")
                            product = port_info.get("product", "")
                            if port:
                                port_id = f"port:{ip}:{port}"
                                label = f"Port {port}" + (f" ({product})" if product else "")
                                nodes.append(NodeModel(id=port_id, label=label, type=NodeTypeEnum.OTHER,
                                                       metadata={"port": port, "product": product}))
                                edges.append(EdgeModel(source=root_id, target=port_id, relation="EXPOSES_PORT",
                                                       confidence=1.0))

                        # Vulns
                        for cve in list(data.get("vulns", {}).keys())[:5]:
                            vuln_id = f"vuln:{cve}"
                            nodes.append(NodeModel(id=vuln_id, label=cve, type=NodeTypeEnum.OTHER,
                                                   metadata={"type": "cve"}))
                            edges.append(EdgeModel(source=root_id, target=vuln_id, relation="VULNERABLE_TO", confidence=0.85))

            except Exception as e:
                log.warning("Shodan API call failed", error=str(e))
                raw["shodan_error"] = str(e)

        # ─── Fallback: Free IP-API.com (no key needed) ────────────────────────
        if not raw or not SHODAN_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    # Use ip-api.com for basic IP info (free, no key)
                    ip_to_lookup = target
                    if target_type == TargetTypeEnum.DOMAIN:
                        # Resolve domain
                        import socket
                        try:
                            ip_to_lookup = socket.gethostbyname(target)
                            dom_id = f"ip:{ip_to_lookup}"
                            nodes.append(NodeModel(id=dom_id, label=ip_to_lookup, type=NodeTypeEnum.IP,
                                                   metadata={"resolved_from": target}))
                            edges.append(EdgeModel(source=root_id, target=dom_id, relation="RESOLVES_TO", confidence=1.0))
                        except Exception:
                            pass

                    resp = await client.get(f"http://ip-api.com/json/{ip_to_lookup}?fields=status,country,regionName,city,isp,org,as,lat,lon")
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "success":
                            raw["ip_api"] = data
                            country = data.get("country", "")
                            city = data.get("city", "")
                            isp = data.get("isp", "")
                            org = data.get("org", "")
                            asn = data.get("as", "")

                            if country:
                                loc_id = f"location:{country.lower().replace(' ', '_')}"
                                label = f"{city}, {country}" if city else country
                                if not any(n.id == loc_id for n in nodes):
                                    nodes.append(NodeModel(id=loc_id, label=label, type=NodeTypeEnum.LOCATION,
                                                           metadata={"country": country, "city": city}))
                                    edges.append(EdgeModel(source=root_id, target=loc_id, relation="LOCATED_IN", confidence=0.9))

                            if isp:
                                isp_id = f"isp:{isp[:30].lower().replace(' ', '_')}"
                                if not any(n.id == isp_id for n in nodes):
                                    nodes.append(NodeModel(id=isp_id, label=isp, type=NodeTypeEnum.OTHER,
                                                           metadata={"type": "isp", "asn": asn}))
                                    edges.append(EdgeModel(source=root_id, target=isp_id, relation="HOSTED_BY", confidence=0.9))
            except Exception as e:
                log.warning("ip-api fallback failed", error=str(e))
                raw["fallback_error"] = str(e)

        status = StatusEnum.SUCCESS if len(nodes) > 1 else StatusEnum.PARTIAL
        return ScanResult(
            scan_id=scan_id, target=target, target_type=target_type,
            module_name=self.name, status=status,
            execution_time_ms=int((time.time() - start) * 1000),
            nodes=nodes, edges=edges, raw_data=raw,
            error=None if SHODAN_API_KEY else "No SHODAN_API_KEY set — using ip-api.com fallback"
        )
