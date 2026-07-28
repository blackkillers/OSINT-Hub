"""OSINT-Hub — Domain/BuiltWith Module (DNS + WHOIS + Tech stack via free APIs)"""

import json
import os
import socket
import time
from uuid import UUID
from typing import List

import httpx
import structlog

from app.modules.base import BaseOSINTModule
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)


class BuiltWithModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "domain_builtwith"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.DOMAIN]

    async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
        start = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        domain = target.lower().strip().removeprefix("http://").removeprefix("https://").split("/")[0]
        root_id = f"domain:{domain}"
        nodes: List[NodeModel] = [
            NodeModel(id=root_id, label=domain, type=NodeTypeEnum.DOMAIN, metadata={"is_target": True})
        ]
        edges: List[EdgeModel] = []
        raw: dict = {}

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                # ── DNS Resolution ─────────────────────────────────
                try:
                    ip = socket.gethostbyname(domain)
                    ip_id = f"ip:{ip}"
                    nodes.append(NodeModel(id=ip_id, label=ip, type=NodeTypeEnum.IP,
                                           metadata={"resolved_from": domain}))
                    edges.append(EdgeModel(source=root_id, target=ip_id, relation="RESOLVES_TO", confidence=1.0))
                    raw["resolved_ip"] = ip
                except Exception:
                    pass

                # ── DNS over HTTPS (MX, NS records) ─────────────────
                try:
                    mx_resp = await client.get(
                        f"https://dns.google/resolve?name={domain}&type=MX",
                        headers={"Accept": "application/json"}
                    )
                    if mx_resp.status_code == 200:
                        mx_data = mx_resp.json()
                        for answer in mx_data.get("Answer", [])[:5]:
                            mx_host = answer.get("data", "").split()[-1].rstrip(".")
                            if mx_host:
                                mx_id = f"mx:{mx_host}"
                                nodes.append(NodeModel(id=mx_id, label=f"MX: {mx_host}", type=NodeTypeEnum.DOMAIN,
                                                       metadata={"type": "mx_record"}))
                                edges.append(EdgeModel(source=root_id, target=mx_id, relation="HAS_MX", confidence=1.0))
                        raw["mx_records"] = [a.get("data") for a in mx_data.get("Answer", [])]
                except Exception:
                    pass

                # ── NS Records ──────────────────────────────────────
                try:
                    ns_resp = await client.get(
                        f"https://dns.google/resolve?name={domain}&type=NS",
                        headers={"Accept": "application/json"}
                    )
                    if ns_resp.status_code == 200:
                        ns_data = ns_resp.json()
                        for answer in ns_data.get("Answer", [])[:4]:
                            ns_host = answer.get("data", "").rstrip(".")
                            if ns_host:
                                ns_id = f"ns:{ns_host}"
                                nodes.append(NodeModel(id=ns_id, label=f"NS: {ns_host}", type=NodeTypeEnum.DOMAIN,
                                                       metadata={"type": "ns_record"}))
                                edges.append(EdgeModel(source=root_id, target=ns_id, relation="HAS_NS", confidence=1.0))
                        raw["ns_records"] = [a.get("data") for a in ns_data.get("Answer", [])]
                except Exception:
                    pass

                # ── Certificate Transparency (crt.sh) ────────────────
                try:
                    crt_resp = await client.get(
                        f"https://crt.sh/?q=%.{domain}&output=json",
                        timeout=15
                    )
                    if crt_resp.status_code == 200:
                        crt_data = crt_resp.json()
                        subdomains = set()
                        for entry in crt_data[:50]:
                            name = entry.get("name_value", "")
                            for subdomain in name.splitlines():
                                subdomain = subdomain.strip().lstrip("*.")
                                if subdomain.endswith(domain) and subdomain != domain:
                                    subdomains.add(subdomain)
                        raw["subdomains_crtsh"] = list(subdomains)[:20]
                        for sub in list(subdomains)[:10]:
                            sub_id = f"domain:{sub}"
                            nodes.append(NodeModel(id=sub_id, label=sub, type=NodeTypeEnum.DOMAIN,
                                                   metadata={"type": "subdomain"}))
                            edges.append(EdgeModel(source=root_id, target=sub_id, relation="HAS_SUBDOMAIN", confidence=0.95))
                except Exception:
                    pass

                # ── SSL/TLS Info ─────────────────────────────────────
                try:
                    ssl_resp = await client.get(f"https://api.ssllabs.com/api/v3/analyze?host={domain}&publish=off&all=on", timeout=10)
                    if ssl_resp.status_code == 200:
                        ssl_data = ssl_resp.json()
                        grade = ssl_data.get("endpoints", [{}])[0].get("grade", "?") if ssl_data.get("endpoints") else "?"
                        raw["ssl_grade"] = grade
                except Exception:
                    pass

                # ── HTTP Headers / Tech detection ────────────────────
                try:
                    site_resp = await client.get(f"https://{domain}", timeout=10)
                    headers = dict(site_resp.headers)
                    raw["http_headers"] = {k: v for k, v in headers.items() if k.lower() in
                                           ("server", "x-powered-by", "x-framework", "cf-ray", "x-cache")}
                    # Server node
                    server = headers.get("server", headers.get("x-powered-by", ""))
                    if server:
                        srv_id = f"tech:server:{server[:30].lower().replace(' ', '_')}"
                        nodes.append(NodeModel(id=srv_id, label=f"Server: {server}", type=NodeTypeEnum.OTHER,
                                               metadata={"type": "technology", "software": server}))
                        edges.append(EdgeModel(source=root_id, target=srv_id, relation="RUNS_ON", confidence=0.9))
                except Exception:
                    pass

        except Exception as exc:
            log.error("Domain module failed", error=str(exc))
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.FAILED,
                execution_time_ms=int((time.time() - start) * 1000),
                error=str(exc)
            )

        return ScanResult(
            scan_id=scan_id, target=target, target_type=target_type,
            module_name=self.name,
            status=StatusEnum.SUCCESS if len(nodes) > 1 else StatusEnum.PARTIAL,
            execution_time_ms=int((time.time() - start) * 1000),
            nodes=nodes, edges=edges, raw_data=raw
        )
