"""Extended Remnawave Panel API mixin (Hosts, Config Profiles, Snippets, Squads, Sub Settings, Infra, Tokens)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemnawavePanelExtrasMixin:
    """Mixin exposing extended Remnawave Panel controllers with unified request/error handling."""

    async def _panel_call(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | list[Any] | None = None,
        fallback_paths: tuple[str, ...] = (),
    ) -> tuple[bool, Any, int]:
        """Execute an HTTP call against Remnawave and unwrap `.response` cleanly."""
        paths = (path, *fallback_paths)
        last_status = 0
        last_err: Any = "ارتباط با پنل برقرار نشد."

        for target in paths:
            try:
                kwargs: dict[str, Any] = {}
                if json is not None:
                    kwargs["json"] = json
                resp = await self._client.request(method.upper(), target, **kwargs)
                last_status = int(getattr(resp, "status_code", 0))
                if last_status in (200, 201, 202, 204):
                    if last_status == 204 or not getattr(resp, "content", b""):
                        return True, {}, last_status
                    try:
                        body = resp.json()
                    except Exception:
                        return True, {}, last_status
                    inner = body.get("response") if isinstance(body, dict) and "response" in body else body
                    return True, inner, last_status

                extract = getattr(self, "_extract_panel_error", None)
                last_err = extract(resp) if callable(extract) else f"HTTP {last_status}"
                if last_status not in (404, 405):
                    return False, last_err, last_status
            except httpx.HTTPError as exc:
                logger.warning("Remnawave %s %s error: %s", method, target, exc)
                last_err = str(exc)
        return False, last_err, last_status

    @staticmethod
    def _extract_list(data: Any, *keys: str) -> list[dict[str, Any]]:
        """Safely extract a list of dicts from varied Remnawave response envelopes."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for k in (*keys, "items", "data", "results"):
                val = data.get(k)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
        return []

    # --- Node Lifecycle & Bulk Actions ---
    async def set_node_enabled(self, node_uuid: str, enabled: bool) -> tuple[bool, str]:
        """Enable or disable a node via Remnawave panel actions."""
        action = "enable" if enabled else "disable"
        ok, res, _ = await self._panel_call("POST", f"/api/nodes/{node_uuid}/actions/{action}", json={})
        if ok:
            return True, "سرور فعال شد." if enabled else "سرور غیرفعال شد."
        return False, str(res)

    async def reset_node_traffic(self, node_uuid: str) -> tuple[bool, str]:
        """Reset consumed traffic counter for a single node."""
        ok, res, _ = await self._panel_call("POST", f"/api/nodes/{node_uuid}/actions/reset-traffic", json={})
        if ok:
            return True, "ترافیک مصرفی سرور ریست شد."
        return False, str(res)

    async def restart_all_nodes(self, *, force_restart: bool = False) -> tuple[bool, str]:
        """Trigger cluster-wide node restart."""
        ok, res, status = await self._panel_call(
            "POST",
            "/api/nodes/actions/restart-all",
            json={"forceRestart": bool(force_restart)},
        )
        if not ok and status == 400 and "forceRestart" in str(res):
            ok, res, _ = await self._panel_call("POST", "/api/nodes/actions/restart-all", json={})
        if ok:
            return True, "دستور ریستارت همه سرورها به پنل ارسال شد."
        return False, str(res)

    # --- Hosts & Bulk Actions ---
    async def get_hosts(self) -> list[dict[str, Any]]:
        """Fetch all hosts configured in the panel."""
        ok, data, _ = await self._panel_call("GET", "/api/hosts")
        return self._extract_list(data, "hosts") if ok else []

    async def _save_host_request(self, method: str, payload: dict[str, Any]) -> tuple[bool, Any]:
        """Send POST/PATCH /api/hosts with legacy excludedInternalSquads fallback (< v3.4)."""
        ok, res, status = await self._panel_call(method, "/api/hosts", json=payload)
        if not ok and status in (400, 422) and "internalSquads" in payload and "internalSquads" in str(res):
            legacy = {k: v for k, v in payload.items() if k != "internalSquads"}
            sq = payload["internalSquads"]
            if isinstance(sq, dict) and sq.get("mode") == "EXCLUDE":
                legacy["excludedInternalSquads"] = list(sq.get("squads") or [])
            ok, res, _ = await self._panel_call(method, "/api/hosts", json=legacy)
        return ok, res

    async def create_host(self, payload: dict[str, Any]) -> tuple[bool, Any]:
        """Create a new host in Remnawave."""
        return await self._save_host_request("POST", payload)

    async def update_host(self, payload: dict[str, Any]) -> tuple[bool, Any]:
        """Update an existing host via PATCH /api/hosts."""
        return await self._save_host_request("PATCH", payload)

    async def delete_host(self, host_uuid: str) -> tuple[bool, Any]:
        """Delete a host by UUID."""
        ok, res, _ = await self._panel_call("DELETE", f"/api/hosts/{host_uuid}")
        return ok, res

    async def bulk_hosts_action(self, action: str, uuids: list[str]) -> tuple[bool, str]:
        """Run bulk enable/disable/delete on a list of host UUIDs."""
        if action not in ("enable", "disable", "delete") or not uuids:
            return False, "عملیات یا لیست هاست نامعتبر است."
        ok, res, _ = await self._panel_call("POST", f"/api/hosts/bulk/{action}", json={"uuids": uuids})
        if ok:
            labels = {"enable": "فعال شدند", "disable": "غیرفعال شدند", "delete": "حذف شدند"}
            return True, f"{len(uuids)} هاست با موفقیت {labels[action]}."
        return False, str(res)

    # --- Config Profiles & Snippets ---
    async def get_config_profiles(self) -> list[dict[str, Any]]:
        """Fetch Xray config profiles and their inbounds."""
        ok, data, _ = await self._panel_call("GET", "/api/config-profiles")
        return self._extract_list(data, "configProfiles", "profiles") if ok else []

    async def get_snippets(self) -> list[dict[str, Any]]:
        """Fetch reusable Xray JSON snippets."""
        ok, data, _ = await self._panel_call("GET", "/api/snippets")
        return self._extract_list(data, "snippets") if ok else []

    async def save_snippet(self, name: str, snippet: Any, *, update: bool = False) -> tuple[bool, Any]:
        """Create or update a Remnawave config snippet."""
        method = "PATCH" if update else "POST"
        ok, res, _ = await self._panel_call(method, "/api/snippets", json={"name": name, "snippet": snippet})
        return ok, res

    async def delete_snippet(self, name: str) -> tuple[bool, Any]:
        """Delete a config snippet by name."""
        ok, res, _ = await self._panel_call(
            "DELETE",
            f"/api/snippets/{name}",
            fallback_paths=("/api/snippets",),
            json={"name": name},
        )
        return ok, res

    # --- Squads (Internal & External), Config Profiles, Node CRUD & Keygen ---
    async def get_external_squads(self) -> list[dict[str, Any]]:
        """Fetch external squads configured on the panel."""
        ok, data, _ = await self._panel_call("GET", "/api/external-squads")
        return self._extract_list(data, "externalSquads", "squads") if ok else []

    async def squad_users_action(
        self, squad_type: str, squad_uuid: str, user_refs: list[Any], *, action: str = "add"
    ) -> tuple[bool, str]:
        """Bulk add or remove users on an internal or external squad (v2 userUuids + v3 userIds)."""
        if action not in ("add", "remove") or not squad_uuid or not user_refs:
            return False, "اطلاعات اسکواد یا کاربران نامعتبر است."

        uuids: list[str] = []
        numeric_ids: list[int] = []
        for item in user_refs:
            if isinstance(item, dict):
                u_str = str(item.get("uuid") or "").strip()
                if u_str:
                    uuids.append(u_str)
                raw_id = item.get("id")
                if raw_id is not None and str(raw_id).isdigit():
                    numeric_ids.append(int(raw_id))
            else:
                val = str(item or "").strip()
                if val.isdigit():
                    numeric_ids.append(int(val))
                elif val:
                    uuids.append(val)

        method = "POST" if action == "add" else "DELETE"
        is_ext = squad_type == "external"
        base = "external-squads" if is_ext else "internal-squads"
        suffix = ("add-users" if action == "add" else "remove-users") if is_ext else (
            "add-many-users" if action == "add" else "remove-many-users"
        )
        alt_suffix = "add-users" if action == "add" else "remove-users"
        fallbacks = () if is_ext else (f"/api/{base}/{squad_uuid}/bulk-actions/{alt_suffix}",)
        path = f"/api/{base}/{squad_uuid}/bulk-actions/{suffix}"

        primary_body: dict[str, Any] = (
            {"userIds": numeric_ids} if (not uuids and numeric_ids) else {"userUuids": uuids}
        )
        ok, res, status = await self._panel_call(method, path, json=primary_body, fallback_paths=fallbacks)
        if not ok and status in (400, 422) and numeric_ids and "userIds" in str(res) and "userIds" not in primary_body:
            ok, res, _ = await self._panel_call(
                method, path, json={"userIds": numeric_ids}, fallback_paths=fallbacks
            )
        elif not ok and status in (400, 422) and uuids and "uuids" in str(res).lower() and "uuids" not in primary_body:
            ok, res, _ = await self._panel_call(method, path, json={"uuids": uuids}, fallback_paths=fallbacks)

        if ok:
            label = "خارجی" if is_ext else "داخلی"
            return True, f"تغییرات اسکواد {label} روی کاربران اعمال شد."
        return False, str(res)

    async def external_squad_users_action(
        self, squad_uuid: str, user_uuids: list[str], *, action: str = "add"
    ) -> tuple[bool, str]:
        """Bulk add or remove users on an external squad."""
        return await self.squad_users_action("external", squad_uuid, user_uuids, action=action)

    async def save_external_squad(
        self,
        name: str,
        *,
        headers_add: dict[str, str] | None = None,
        headers_remove: list[str] | None = None,
        squad_uuid: str | None = None,
    ) -> tuple[bool, Any]:
        """Create or update a Remnawave external squad."""
        clean_name = str(name or "").strip()
        if not clean_name:
            return False, "نام اسکواد خارجی الزامی است."
        payload: dict[str, Any] = {"name": clean_name}
        if squad_uuid:
            payload["uuid"] = str(squad_uuid).strip()
        if headers_add:
            payload["responseHeadersAdd"] = headers_add
        if headers_remove:
            payload["responseHeadersRemove"] = headers_remove
        method = "PATCH" if squad_uuid else "POST"
        ok, res, status = await self._panel_call(method, "/api/external-squads", json=payload)
        if not ok and status in (400, 422) and ("responseHeadersAdd" in payload or "responseHeadersRemove" in payload):
            minimal = {k: v for k, v in payload.items() if k in ("uuid", "name")}
            ok, res, _ = await self._panel_call(method, "/api/external-squads", json=minimal)
        return ok, res

    async def delete_external_squad(self, squad_uuid: str) -> tuple[bool, Any]:
        """Delete an external squad by UUID."""
        clean_uuid = str(squad_uuid or "").strip()
        if not clean_uuid:
            return False, "شناسه اسکواد خارجی الزامی است."
        ok, res, _ = await self._panel_call("DELETE", f"/api/external-squads/{clean_uuid}")
        return ok, res

    async def save_config_profile(
        self, name: str, config: dict[str, Any], *, profile_uuid: str | None = None
    ) -> tuple[bool, Any]:
        """Create or update an Xray config profile in Remnawave."""
        clean_name = str(name or "").strip()
        if not clean_name or not isinstance(config, dict):
            return False, "نام و ساختار JSON پروفایل معتبر نیست."
        payload: dict[str, Any] = {"name": clean_name, "config": config}
        if profile_uuid:
            payload["uuid"] = str(profile_uuid).strip()
            ok, res, _ = await self._panel_call("PATCH", "/api/config-profiles", json=payload)
        else:
            ok, res, _ = await self._panel_call("POST", "/api/config-profiles", json=payload)
        return ok, res

    async def delete_config_profile(self, profile_uuid: str) -> tuple[bool, Any]:
        """Delete a config profile by UUID."""
        clean_uuid = str(profile_uuid or "").strip()
        if not clean_uuid:
            return False, "شناسه پروفایل الزامی است."
        ok, res, _ = await self._panel_call("DELETE", f"/api/config-profiles/{clean_uuid}")
        return ok, res

    async def get_node_keygen(self) -> tuple[bool, Any]:
        """Fetch cryptographic pairing secret/public key from Remnawave /api/keygen."""
        ok, res, _ = await self._panel_call("GET", "/api/keygen")
        return ok, res

    async def create_node(self, payload: dict[str, Any]) -> tuple[bool, Any]:
        """Register a new node via POST /api/nodes."""
        ok, res, status = await self._panel_call("POST", "/api/nodes", json=payload)
        if not ok and status in (400, 422) and "configProfile" in payload and "configProfile" in str(res):
            flat = {k: v for k, v in payload.items() if k != "configProfile"}
            cp = payload["configProfile"]
            if isinstance(cp, dict) and cp.get("activeConfigProfileUuid"):
                flat["configProfileUuid"] = cp["activeConfigProfileUuid"]
            ok, res, _ = await self._panel_call("POST", "/api/nodes", json=flat)
        return ok, res

    async def delete_node(self, node_uuid: str) -> tuple[bool, Any]:
        """Delete a node from Remnawave panel by UUID."""
        clean_uuid = str(node_uuid or "").strip()
        if not clean_uuid:
            return False, "شناسه نود الزامی است."
        ok, res, _ = await self._panel_call("DELETE", f"/api/nodes/{clean_uuid}")
        return ok, res

    async def save_internal_squad(
        self, name: str, inbounds: list[str], *, squad_uuid: str | None = None
    ) -> tuple[bool, Any]:
        """Create or update an internal squad and its allowed inbound UUIDs."""
        clean_name = str(name or "").strip()
        clean_inbounds = [str(x).strip() for x in (inbounds or []) if str(x).strip()]
        if not clean_name:
            return False, "نام اسکواد داخلی الزامی است."
        if squad_uuid:
            payload = {"uuid": str(squad_uuid).strip(), "name": clean_name, "inbounds": clean_inbounds}
            ok, res, _ = await self._panel_call("PATCH", "/api/internal-squads", json=payload)
        else:
            payload = {"name": clean_name, "inbounds": clean_inbounds}
            ok, res, _ = await self._panel_call("POST", "/api/internal-squads", json=payload)
        return ok, res

    async def delete_internal_squad(self, squad_uuid: str) -> tuple[bool, Any]:
        """Delete an internal squad by UUID."""
        clean_uuid = str(squad_uuid or "").strip()
        if not clean_uuid:
            return False, "شناسه اسکواد داخلی الزامی است."
        ok, res, _ = await self._panel_call("DELETE", f"/api/internal-squads/{clean_uuid}")
        return ok, res

    async def get_subscription_settings(self) -> dict[str, Any]:
        """Fetch global panel subscription settings."""
        ok, data, _ = await self._panel_call("GET", "/api/subscription-settings")
        return data if ok and isinstance(data, dict) else {}

    async def update_subscription_settings(self, payload: dict[str, Any]) -> tuple[bool, Any]:
        """Update global panel subscription settings."""
        ok, res, _ = await self._panel_call("PATCH", "/api/subscription-settings", json=payload)
        return ok, res

    # --- Full Infra Billing Providers & Panel Node Records ---
    async def create_infra_provider(
        self, name: str, *, favicon_link: str | None = None, login_url: str | None = None
    ) -> tuple[bool, Any]:
        """Create an infra billing provider in Remnawave."""
        body: dict[str, Any] = {"name": name}
        if favicon_link:
            body["faviconLink"] = favicon_link
        if login_url:
            body["loginUrl"] = login_url
        ok, res, _ = await self._panel_call("POST", "/api/infra-billing/providers", json=body)
        return ok, res

    async def update_infra_provider(
        self,
        provider_uuid: str,
        *,
        name: str | None = None,
        favicon_link: str | None = None,
        login_url: str | None = None,
    ) -> tuple[bool, Any]:
        """Update an infra billing provider in Remnawave."""
        body: dict[str, Any] = {"uuid": provider_uuid}
        if name is not None:
            body["name"] = name
        if favicon_link is not None:
            body["faviconLink"] = favicon_link or None
        if login_url is not None:
            body["loginUrl"] = login_url or None
        ok, res, _ = await self._panel_call("PATCH", "/api/infra-billing/providers", json=body)
        return ok, res

    async def delete_infra_provider(self, provider_uuid: str) -> tuple[bool, Any]:
        """Delete an infra billing provider from Remnawave."""
        ok, res, _ = await self._panel_call("DELETE", f"/api/infra-billing/providers/{provider_uuid}")
        return ok, res

    async def get_infra_billing_nodes(self) -> list[dict[str, Any]]:
        """Fetch infra billing node records stored in Remnawave."""
        ok, data, _ = await self._panel_call("GET", "/api/infra-billing/nodes")
        return self._extract_list(data, "nodes", "billingNodes") if ok else []

    async def sync_infra_billing_node(
        self, provider_uuid: str, node_uuid: str, *, next_billing_at: str | None = None
    ) -> tuple[bool, Any]:
        """Create or update node infra-billing linkage in Remnawave panel."""
        clean_prov = str(provider_uuid or "").strip()
        clean_node = str(node_uuid or "").strip()
        existing = await self.get_infra_billing_nodes()
        matched = next(
            (
                x
                for x in existing
                if str(x.get("nodeUuid") or (x.get("node") or {}).get("uuid") or "") == clean_node
            ),
            None,
        )
        eff_next = next_billing_at or (matched.get("nextBillingAt") if isinstance(matched, dict) else None)

        if matched and matched.get("uuid"):
            matched_prov = str(
                matched.get("providerUuid") or (matched.get("provider") or {}).get("uuid") or ""
            ).strip()
            if clean_prov and matched_prov and matched_prov != clean_prov:
                if not eff_next:
                    return False, "برای تغییر ارائه‌دهنده در پنل، تاریخ سررسید بعدی الزامی است."
                ok_del, res_del, _ = await self._panel_call(
                    "DELETE", f"/api/infra-billing/nodes/{matched['uuid']}"
                )
                if not ok_del:
                    return False, res_del
                ok, res, _ = await self._panel_call(
                    "POST",
                    "/api/infra-billing/nodes",
                    json={"providerUuid": clean_prov, "nodeUuid": clean_node, "nextBillingAt": eff_next},
                )
                return ok, res

            if not eff_next:
                return False, "تاریخ سررسید بعدی برای همگام‌سازی با پنل الزامی است."
            # UpdateInfraBillingNodeRequestDto only accepts uuid (or uuids) + nextBillingAt (rejects providerUuid)
            patch_body: dict[str, Any] = {"uuid": matched["uuid"], "nextBillingAt": eff_next}
            ok, res, status = await self._panel_call("PATCH", "/api/infra-billing/nodes", json=patch_body)
            if not ok and status in (400, 422) and "uuids" in str(res):
                ok, res, _ = await self._panel_call(
                    "PATCH",
                    "/api/infra-billing/nodes",
                    json={"uuids": [matched["uuid"]], "nextBillingAt": eff_next},
                )
            return ok, res

        if not clean_prov:
            return False, "برای ثبت سرور در بخش Infra Billing پنل، انتخاب ارائه‌دهنده الزامی است."
        if not eff_next:
            return False, "برای ثبت اولیه سرور در Infra Billing پنل، تاریخ سررسید بعدی الزامی است."
        ok, res, _ = await self._panel_call(
            "POST",
            "/api/infra-billing/nodes",
            json={"providerUuid": clean_prov, "nodeUuid": clean_node, "nextBillingAt": eff_next},
        )
        return ok, res

    async def get_infra_billing_history(self) -> list[dict[str, Any]]:
        """Fetch infra billing history records (Bill Records) from Remnawave."""
        ok, data, _ = await self._panel_call("GET", "/api/infra-billing/history")
        return self._extract_list(data, "records", "bills", "history", "billingHistory") if ok else []

    async def create_infra_billing_record(
        self, provider_uuid: str, amount: float, billed_at: str
    ) -> tuple[bool, Any]:
        """Create a billing payment record in Remnawave /api/infra-billing/history."""
        body = {
            "providerUuid": str(provider_uuid).strip(),
            "amount": round(float(amount), 4),
            "billedAt": str(billed_at).strip(),
        }
        ok, res, _ = await self._panel_call("POST", "/api/infra-billing/history", json=body)
        return ok, res

    async def delete_infra_billing_record(self, record_uuid: str) -> tuple[bool, Any]:
        """Delete an infra billing history record by UUID."""
        ok, res, _ = await self._panel_call("DELETE", f"/api/infra-billing/history/{record_uuid}")
        return ok, res

    # --- API Tokens (requires Admin JWT on panel) ---
    async def get_api_tokens(self) -> dict[str, Any]:
        """Fetch API tokens from panel, distinguishing Admin-JWT restriction."""
        ok, data, status = await self._panel_call("GET", "/api/tokens")
        if ok:
            return {"ok": True, "tokens": self._extract_list(data, "apiKeys", "tokens"), "jwt_required": False}
        return {
            "ok": False,
            "tokens": [],
            "jwt_required": status in (401, 403),
            "error": str(data),
        }

    async def create_api_token(self, token_name: str) -> tuple[bool, Any]:
        """Create a new panel API token (requires Admin JWT)."""
        ok, res, _ = await self._panel_call("POST", "/api/tokens", json={"tokenName": token_name})
        return ok, res

    async def delete_api_token(self, token_uuid: str) -> tuple[bool, Any]:
        """Revoke/delete a panel API token (requires Admin JWT)."""
        ok, res, _ = await self._panel_call("DELETE", f"/api/tokens/{token_uuid}")
        return ok, res
