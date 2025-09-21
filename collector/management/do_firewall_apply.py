#!/usr/bin/env python3
"""
DigitalOcean Cloud Firewall one-shot setup

Назначение:
- Создать или обновить firewall с именем (по умолчанию) 'orderbook-collector-fw'
- Открыть TCP 22 (SSH) из заданных источников
- Открыть TCP 8000 (мониторинг) только из заданных источников
- Привязать firewall к заданному Droplet (по ID или имени)

Запуск (пример):
  DO_TOKEN=... \
  DO_DROPLET_ID=123456789 \
  DO_ALLOW_8000_SOURCES="203.0.113.10/32,198.51.100.0/24" \
  python3 collector/management/do_firewall_apply.py

Параметры можно передать и через CLI флаги, см. --help.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

import requests

API_BASE = "https://api.digitalocean.com/v2"


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "orderbook-collector/DO-firewall-setup",
    }


def _split_sources(csv: str) -> List[str]:
    return [x.strip() for x in csv.split(",") if x.strip()]


def resolve_droplet_id(token: str, droplet_id: Optional[str], droplet_name: Optional[str], droplet_ip: Optional[str]) -> int:
    if droplet_id:
        try:
            return int(droplet_id)
        except ValueError:
            raise SystemExit("DO_DROPLET_ID must be integer")

    # Разрешение по IP (если передан)
    if droplet_ip:
        resp = requests.get(
            f"{API_BASE}/droplets",
            headers=_headers(token),
            params={"per_page": 200},
            timeout=20,
        )
        resp.raise_for_status()
        droplets = resp.json().get("droplets", [])
        for d in droplets:
            for net in d.get("networks", {}).get("v4", []):
                if net.get("ip_address") == droplet_ip:
                    return int(d["id"])
        raise SystemExit(f"Droplet with public IP '{droplet_ip}' not found")

    if not droplet_name:
        raise SystemExit("Either DO_DROPLET_ID or DO_DROPLET_NAME or DO_DROPLET_IP must be provided")

    # По имени может быть несколько, DigitalOcean возвращает список
    resp = requests.get(
        f"{API_BASE}/droplets",
        headers=_headers(token),
        params={"name": droplet_name, "per_page": 200},
        timeout=20,
    )
    resp.raise_for_status()
    droplets = resp.json().get("droplets", [])
    if not droplets:
        raise SystemExit(f"Droplet with name '{droplet_name}' not found")
    if len(droplets) > 1:
        # Берём первый и предупреждаем
        print(f"[WARN] Multiple droplets named '{droplet_name}' found, using id={droplets[0]['id']}")
    return int(droplets[0]["id"])


def find_firewall_by_name(token: str, name: str) -> Optional[Dict]:
    resp = requests.get(
        f"{API_BASE}/firewalls", headers=_headers(token), params={"per_page": 200}, timeout=20
    )
    resp.raise_for_status()
    for fw in resp.json().get("firewalls", []):
        if fw.get("name") == name:
            return fw
    return None


def build_payload(
    name: str,
    droplet_ids: List[int],
    allow_ssh_sources: List[str],
    allow_8000_sources: List[str],
    enable_ipv6: bool = False,
) -> Dict:
    if not allow_8000_sources:
        raise SystemExit("DO_ALLOW_8000_SOURCES is required (at least one CIDR/IP)")

    inbound_rules = [
        {
            "protocol": "tcp",
            "ports": "22",
            "sources": {"addresses": allow_ssh_sources or ["0.0.0.0/0"]},
        },
        {
            "protocol": "tcp",
            "ports": "8000",
            "sources": {"addresses": allow_8000_sources},
        },
    ]

    # Разрешаем исходящий трафик целиком (стандартный шаблон)
    dest_addresses_v4 = ["0.0.0.0/0"]
    dest_addresses_v6 = ["::/0"] if enable_ipv6 else []
    outbound_rules = [
        {
            "protocol": "icmp",
            "destinations": {"addresses": dest_addresses_v4 + dest_addresses_v6},
        },
        {
            "protocol": "tcp",
            "ports": "0",
            "destinations": {"addresses": dest_addresses_v4 + dest_addresses_v6},
        },
        {
            "protocol": "udp",
            "ports": "0",
            "destinations": {"addresses": dest_addresses_v4 + dest_addresses_v6},
        },
    ]

    return {
        "name": name,
        "droplet_ids": droplet_ids,
        "inbound_rules": inbound_rules,
        "outbound_rules": outbound_rules,
    }


def create_firewall(token: str, payload: Dict) -> Dict:
    resp = requests.post(f"{API_BASE}/firewalls", headers=_headers(token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_firewall(token: str, fw_id: str, payload: Dict) -> Dict:
    resp = requests.put(f"{API_BASE}/firewalls/{fw_id}", headers=_headers(token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Apply DigitalOcean Cloud Firewall for OrderBook Collector")
    parser.add_argument("--firewall-name", default=os.getenv("DO_FIREWALL_NAME", "orderbook-collector-fw"))
    parser.add_argument("--droplet-id", default=os.getenv("DO_DROPLET_ID"))
    parser.add_argument("--droplet-name", default=os.getenv("DO_DROPLET_NAME"))
    parser.add_argument("--droplet-ip", default=os.getenv("DO_DROPLET_IP"))
    parser.add_argument("--allow-8000", default=os.getenv("DO_ALLOW_8000_SOURCES", ""))
    parser.add_argument("--allow-ssh", default=os.getenv("DO_ALLOW_SSH_SOURCES", "0.0.0.0/0"))
    parser.add_argument("--enable-ipv6", action="store_true", default=os.getenv("DO_ENABLE_IPV6", "false").lower() == "true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    # Читаем токен из DO_TOKEN или, как fallback, DG_OC_TOKEN
    token = os.getenv("DO_TOKEN") or os.getenv("DG_OC_TOKEN")
    if not token:
        raise SystemExit("DO_TOKEN (или DG_OC_TOKEN) environment variable is required")

    # Resolve droplet id
    droplet_id = resolve_droplet_id(token, args.droplet_id, args.droplet_name, args.droplet_ip)

    allow_8000_sources = _split_sources(args.allow_8000)
    allow_ssh_sources = _split_sources(args.allow_ssh) or ["0.0.0.0/0"]

    payload = build_payload(
        name=args.firewall_name,
        droplet_ids=[droplet_id],
        allow_ssh_sources=allow_ssh_sources,
        allow_8000_sources=allow_8000_sources,
        enable_ipv6=args.enable_ipv6,
    )

    if args.dry_run:
        print(json.dumps({"dry_run": True, "payload": payload}, indent=2))
        return

    # Find existing firewall
    existing = find_firewall_by_name(token, args.firewall_name)

    if not existing:
        result = create_firewall(token, payload)
        print(json.dumps({"action": "created", "result": result}, indent=2))
        return

    # Если firewall уже есть: не удаляем чужие дроплеты без необходимости.
    # Объединяем текущие droplet_ids с целевым.
    current_ids = set(existing.get("droplet_ids", []))
    current_ids.add(droplet_id)
    payload["droplet_ids"] = sorted(list(current_ids))

    result = update_firewall(token, existing["id"], payload)
    print(json.dumps({"action": "updated", "firewall_id": existing["id"], "result": result}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        # Вывод тела ответа для диагностики
        if e.response is not None:
            try:
                detail = e.response.json()
            except Exception:
                detail = e.response.text
            print(f"HTTPError: {e} -> {detail}", file=sys.stderr)
        else:
            print(f"HTTPError: {e}", file=sys.stderr)
        sys.exit(1)
    except SystemExit as e:
        # Передаём код выхода дальше
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
