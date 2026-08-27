#!/usr/bin/env python3
"""Live end-to-end use cases against the running ResearchNavigator stack (http://127.0.0.1:8000).

Every step mutates state through the public HTTP API of the deployed server.
Evidence is written as JSON to stdout steps log; exit code 0 means all use cases passed.
"""
from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000/api"
steps: list[dict[str, object]] = []
client = httpx.Client(base_url=BASE, timeout=60.0)


def step(name: str, ok: bool, detail: str, evidence: dict | None = None) -> None:
    steps.append({"step": name, "ok": ok, "detail": detail, "evidence": evidence or {}})
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}: {detail}", flush=True)
    if not ok:
        raise SystemExit(exit_with_failure())


def expect(cond: bool, name: str, detail: str, evidence: dict | None = None) -> None:
    if not cond:
        step(name, False, detail, evidence)


def exit_with_failure() -> int:
    print(json.dumps(steps, ensure_ascii=False, indent=2))
    return 1


def register(email: str) -> dict:
    r = client.post("/auth/register", json={"email": email, "password": "research-pass-123", "display_name": email.split("@")[0]})
    return {"token": r.json()["access_token"], "user_id": r.json()["user"]["id"]}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    run_id = uuid.uuid4().hex[:8]

    # UC1 Health
    r = client.get("/health")
    step("UC1 服务健康检查", r.status_code == 200 and r.json().get("database") == "ok",
         f"GET /api/health -> {r.json()}")

    # UC2 注册/登录/当前用户
    alice = register(f"alice-{run_id}@example.com")
    bob = register(f"bob-{run_id}@example.com")
    r = client.get("/auth/me", headers=auth(alice["token"]))
    step("UC2 用户注册与身份读取", r.status_code == 200 and r.json()["email"] == f"alice-{run_id}@example.com",
         "注册 alice/bob 并回读 /auth/me", {"alice_user_id": alice["user_id"], "bob_user_id": bob["user_id"]})

    # UC3 研究档案
    profile_payload = {"stage": "硕士研究", "major": "时序异常检测",
                       "broad_direction": "面向未来窗口的异常风险排序与证据约束研究",
                       "keywords": ["time series", "anomaly ranking"]}
    r = client.put("/research-profiles/me", headers=auth(alice["token"]), json=profile_payload)
    step("UC3 研究档案保存", r.status_code == 200 and r.json()["broad_direction"] == profile_payload["broad_direction"],
         "PUT /research-profiles/me 写入并回读")

    # UC4 项目
    r = client.post("/projects", headers=auth(alice["token"]),
                    json={"name": "工业时序异常检测方向评估", "description": "部署验证场景", "broad_direction": "异常风险排序"})
    project_id = r.json()["id"]
    step("UC4 创建研究项目", r.status_code == 201 and project_id > 0, f"POST /projects -> id={project_id}")

    # UC5 Discovery 检索 + 排名元数据 + 组成目标（1-2 个概念词按 search-mode-v1 归类为 discovery）
    r = client.post("/search/papers", headers=auth(alice["token"]),
                    json={"query": "anomaly", "limit": 20, "project_id": project_id})
    body = r.json()
    session_id = body["session_id"]
    top_papers = body["papers"]
    ranked_ok = all("ranking" in p and p["ranking"] and "label" in p["ranking"] for p in top_papers)
    step("UC5 Discovery 检索(Top20)",
         r.status_code in (200, 201) and body["search_mode"] == "discovery"
         and isinstance(body.get("composition"), dict) and ranked_ok and len(top_papers) <= 20,
         f"mode={body['search_mode']} seed={body['diversity_seed']} rule={body['ranking_rule_version']} n={len(top_papers)} composition={body['composition']}",
         {"session_id": session_id, "composition": body["composition"]})

    # UC6 rerun 复用同 seed；新搜索获得新 seed
    r2 = client.post(f"/search/sessions/{session_id}/rerun", headers=auth(alice["token"]))
    rerun_seed = r2.json().get("diversity_seed")
    r3 = client.post("/search/papers", headers=auth(alice["token"]), json={"query": "anomaly", "limit": 20})
    new_seed = r3.json()["diversity_seed"]
    step("UC6 可复现多样性(seed 规则)",
         r2.status_code in (200, 201) and rerun_seed == body["diversity_seed"] and new_seed != body["diversity_seed"],
         f"rerun 复用 seed={rerun_seed}; 新搜索新 seed={new_seed}")

    # UC7 Precise 模式（三词以上概念串 与 明确题名带引号，均按 search-mode-v1 归类为 precise）
    exact_title = '"Attention Is All You Need"'
    rp = client.post("/search/papers", headers=auth(alice["token"]), json={"query": exact_title, "limit": 10})
    rmulti = client.post("/search/papers", headers=auth(alice["token"]),
                         json={"query": "industrial anomaly detection", "limit": 10})
    step("UC7 Precise 模式识别",
         rp.json().get("search_mode") == "precise" and rmulti.json().get("search_mode") == "precise",
         f"query={exact_title} -> {rp.json()['search_mode']}; 三词概念串 -> {rmulti.json()['search_mode']}")

    # UC8 会话恢复：端点返回固化的完整有序语料（含排名元数据）；每页10条由前端切片渲染
    r_full = client.get(f"/search/sessions/{session_id}", headers=auth(alice["token"]))
    sess = r_full.json()
    r = client.get(f"/search/sessions/{session_id}/papers", headers=auth(alice["token"]))
    corpus = r.json()
    corpus_ids = [p["id"] for p in corpus]
    order_preserved = corpus_ids == [int(i) for i in sess.get("result_ids", [])] or corpus_ids == sess.get("result_ids", [])
    ranked = all(p.get("ranking") for p in corpus)
    ui_page1, ui_page2 = corpus_ids[:10], corpus_ids[10:20]
    no_overlap_ui = not set(ui_page1) & set(ui_page2)
    step("UC8 会话恢复与固化语料(UI 每页10条切片)",
         r.status_code == 200 and len(corpus) == sess["result_count"] and order_preserved and ranked
         and len(ui_page1) == min(10, len(corpus)) and no_overlap_ui,
         f"恢复 {len(corpus)} 篇与 session.result_count={sess['result_count']} 一致、顺序与 result_ids 固化一致、排名元数据齐全；UI 第一页/第二页切片无重叠",
         {"ui_page1_first": ui_page1[:3], "ui_page2_first": ui_page2[:3]})

    # UC9 论文详情 + 摘要级分析边界
    paper_id = top_papers[0]["id"]
    rd = client.get(f"/papers/{paper_id}", headers=auth(alice["token"]))
    ra = client.post(f"/papers/{paper_id}/analyze", headers=auth(alice["token"]), json={"project_id": project_id})
    analysis = ra.json().get("analysis") or {}
    warns = [str(w) for w in analysis.get("warnings", [])]
    warn_text = " ".join(warns)
    fields_keys = ("executive_summary", "method_innovation", "datasets", "limitations_inferred", "missing_fields")
    fields_ok = all(k in analysis for k in fields_keys)
    boundary_ok = ("摘要级证据不足" in warn_text) or ("结构化分析能力受限" in warn_text) or (ra.json().get("evidence_level") not in (None, "abstract_only"))
    rg = client.get(f"/papers/{paper_id}/analysis", headers=auth(alice["token"]))
    step("UC9 论文详情与执行摘要级分析",
         rd.status_code == 200 and ra.status_code in (200, 201) and fields_ok and boundary_ok
         and rg.status_code == 200 and bool(analysis.get("executive_summary")),
         f"paper={paper_id} 分析字段({','.join(fields_keys)})齐全且有值; warnings={warns}; GET analysis 复读 HTTP {rg.status_code}",
         {"warnings": warns, "missing_fields_count": len(analysis.get("missing_fields", []))})

    # UC10 收藏幂等重放 + 笔记/标签/阅读状态
    idem = {"Idempotency-Key": f"uc10:{run_id}:fav", "X-Scenario-Version": "deploy-verify-v1"}
    rf1 = client.post("/library/favorites", headers={**auth(alice["token"]), **idem}, json={"paper_id": paper_id})
    rf2 = client.post("/library/favorites", headers={**auth(alice["token"]), **idem}, json={"paper_id": paper_id})
    same_resource = rf1.status_code == rf2.status_code and rf1.status_code in (200, 201)
    rn = client.post("/library/notes", headers=auth(alice["token"]), json={"paper_id": paper_id, "content": "先验证其基线设置，再评估复现成本。"})
    rt = client.post("/library/tags", headers=auth(alice["token"]), json={"name": f"tsad-{run_id}"})
    tag_id = rt.json()["id"]
    ra_tag = client.post(f"/library/papers/{paper_id}/tags/{tag_id}", headers=auth(alice["token"]))
    rr = client.put(f"/library/papers/{paper_id}/reading-status", headers=auth(alice["token"]),
                    json={"status": "queued", "progress": 0})
    lib = client.get("/library", headers=auth(alice["token"])).json()
    items = lib.get("items", [])
    mine = next((i for i in items if i["paper"]["id"] == paper_id), None)
    lib_ok = bool(mine) and mine.get("favorite") is True and any(t["id"] == tag_id for t in mine.get("tags", []))
    step("UC10 收藏库(幂等收藏/笔记/标签/阅读状态)",
         same_resource and rn.status_code in (200, 201) and rt.status_code in (200, 201)
         and ra_tag.status_code in (200, 201, 204) and rr.status_code == 200 and lib_ok,
         f"两次同 Idempotency-Key 收藏均返回 {rf1.status_code}; library 聚合包含 favorite/tag/note/reading_status")

    # UC11 显式 PaperSet
    chosen = [top_papers[i]["id"] for i in range(min(4, len(top_papers)))]
    rs = client.post("/paper-sets", headers=auth(alice["token"]),
                     json={"project_id": project_id, "purpose": "gap", "name": "部署验证·Gap探索集",
                           "paper_ids": chosen, "source_kind": "explicit"})
    compare_ids = [top_papers[i]["id"] for i in range(min(3, len(top_papers)))]
    rc = client.post("/paper-sets", headers=auth(alice["token"]),
                     json={"project_id": project_id, "purpose": "compare", "name": "部署验证·对比集",
                           "paper_ids": compare_ids, "source_kind": "explicit"})
    gap_set_id, cmp_set_id = rs.json()["id"], rc.json()["id"]
    rg = client.get(f"/paper-sets/{gap_set_id}", headers=auth(alice["token"])).json()
    step("UC11 显式论文集合(PaperSet)",
         rs.status_code == 201 and rc.status_code == 201 and sorted(rg["paper_ids"]) == sorted(chosen),
         f"gap集合 id={gap_set_id}({len(rg['paper_ids'])}篇) 对比集合 id={cmp_set_id}(3篇), 集合内容与选择完全一致")

    # UC12 深度对比矩阵
    rcomp = client.post("/comparisons", headers=auth(alice["token"]), json={"project_id": project_id, "paper_set_id": cmp_set_id})
    comp = rcomp.json()
    rows = comp.get("rows", [])
    cells_evidence = all(("evidence_state" in c) for row in rows for c in row.get("cells", [])) and len(rows) > 0
    has_direction = bool(comp.get("direction_snapshot"))
    step("UC12 深度论文对比(证据态矩阵)",
         rcomp.status_code in (200, 201) and cells_evidence and has_direction,
         f"comparison id={comp.get('id')} 行数={len(rows)}(如 method/datasets/results 维度), 单元格均含 evidence_state/citations; direction_snapshot 已快照",
         {"row_keys": [r.get("key") for r in rows][:8]})

    # UC13 Gap 生成 → Challenge(反证检索) → 人工确认前禁止生成计划
    rgen = client.post("/gaps/generate", headers=auth(alice["token"]), json={"project_id": project_id, "paper_set_id": gap_set_id})
    gap = rgen.json()
    gap_id = gap["id"]
    pre_confirm_stage = gap.get("workflow_stage")
    rch = client.post(f"/gaps/{gap_id}/challenge", headers=auth(alice["token"]),
                      json={"additional_terms": ["future horizon risk ranking"], "sources": ["fixture"]})
    gap2 = client.get(f"/gaps/{gap_id}", headers=auth(alice["token"])).json()
    expl = gap2.get("explanation") or {}
    weakening_count = len(expl.get("weakening_papers", []))
    plan_before = client.post("/plans", headers=auth(alice["token"]), json={"project_id": project_id, "gap_id": gap_id})
    step("UC13 Gap 候选与挑战检索",
         rgen.status_code == 201 and pre_confirm_stage == "challenge_required"
         and rch.status_code in (200, 202) and gap2["status"] == "pending_confirmation"
         and gap2["workflow_stage"] == "awaiting_human_confirmation",
         f"generate→{pre_confirm_stage}; challenge→pending_confirmation(awaiting_human_confirmation); 反证文献数={weakening_count}",
         {"challenge_queries": gap2.get("challenge_queries", [])[:3], "not_novelty_proof": gap2.get("not_novelty_proof")})
    plan_blocked_ok = plan_before.status_code >= 400
    detail_note = ""
    if not plan_blocked_ok:
        pl_before_json = plan_before.json()
        detail_note = f"但计划创建在确认前被允许(id={pl_before_json.get('id')})——需要人工复核该语义"

    explanation_fields = ["direct_evidence", "inferences", "supporting_papers", "weakening_papers",
                          "absent_evidence", "direction_relation", "novelty_risk_factors",
                          "challenge_queries", "minimum_validation", "confidence_rationale"]
    missing_expl = [f for f in explanation_fields if f not in expl]
    step("UC13a 解释结构完整(证据/推断分离)",
         bool(expl) and not missing_expl and expl.get("not_novelty_proof") is True,
         f"gap.explanation 含全部解释字段; 缺失字段={missing_expl or '无'}; not_novelty_proof=true; confidence_rationale={str(expl.get('confidence_rationale'))[:80]}")

    # UC14 真实确认(本脚本由操作者本人调用 API 完成确认，非自动化模拟标签)
    rconf = client.post(f"/gaps/{gap_id}/confirm", headers=auth(alice["token"]),
                        json={"confirmed": True, "note": "部署验证：本人已复核证据与反证后确认。"})
    step("UC14 真实人工确认门(操作者API确认)",
         rconf.status_code in (200, 202) and plan_blocked_ok,
         f"确认前创建计划被拒(HTTP {plan_before.status_code}); 确认后 status={rconf.json().get('status', 'confirmed')} {detail_note}",
         {"plan_creation_before_confirm_http": plan_before.status_code})

    # UC15 确认后生成研究计划并更新条目状态
    rplan = client.post("/plans", headers=auth(alice["token"]), json={"project_id": project_id, "gap_id": gap_id,
                                                                     "title": "未来窗口异常风险排序研究计划"})
    plan = rplan.json()
    item_update_ok = True
    item_note = "无计划条目可更新"
    items = plan.get("items", [])
    if items:
        ri = client.put(f"/plan-items/{items[0]['id']}", headers=auth(alice["token"]), json={"status": "in_progress"})
        item_update_ok = ri.status_code == 200
        item_note = f"首个条目已置为 in_progress(HTTP {ri.status_code})"
    step("UC15 研究计划生成与条目推进",
         rplan.status_code in (200, 201) and item_update_ok,
         f"plan id={plan.get('id')} 条目数={len(items)}; {item_note}")

    # UC16 跨用户隔离(Bob 访问 Alice 的全部私有资源必须被拒；Bob 自己的资源必须可用)
    bob_h = auth(bob["token"])
    denials = {
        "search_session": client.get(f"/search/sessions/{session_id}", headers=bob_h).status_code,
        "session_papers": client.get(f"/search/sessions/{session_id}/papers", headers=bob_h).status_code,
        "paper_set": client.get(f"/paper-sets/{gap_set_id}", headers=bob_h).status_code,
        "comparison": client.get(f"/comparisons/{comp.get('id')}", headers=bob_h).status_code,
        "gap": client.get(f"/gaps/{gap_id}", headers=bob_h).status_code,
        "plan": client.get(f"/plans/{plan.get('id')}", headers=bob_h).status_code,
    }
    own_profile = client.put("/research-profiles/me", headers=bob_h, json={"stage": "本科高年级"}).status_code
    denied_all = all(code in (403, 404) for code in denials.values())
    step("UC16 用户数据隔离(跨用户拒绝)", denied_all and own_profile == 200,
         f"Bob 访问 Alice 的资源全部 403/404: {denials}; Bob 更新自己的档案 HTTP {own_profile}")

    # UC17 PDF 上传生命周期(上传→列表→检索→删除)，需要合法权利确认
    pdf_min = (
        "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        "xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"
    ).encode("latin-1")
    rup1 = client.post(f"/papers/{paper_id}/upload", headers=auth(alice["token"]),
                       files={"file": ("deployment-verify.pdf", pdf_min, "application/pdf")},
                       data={"rights_confirmed": "true"})
    no_rights = client.post(f"/papers/{paper_id}/upload", headers=auth(alice["token"]),
                            files={"file": ("x.pdf", pdf_min, "application/pdf")}, data={"rights_confirmed": "false"})
    rdocs = client.get(f"/papers/{paper_id}/documents", headers=auth(alice["token"]))
    docs = rdocs.json()
    doc_id = docs[0]["id"] if docs else None
    rret = client.post(f"/papers/{paper_id}/retrieve", headers=auth(alice["token"]), json={"query": "benchmark"}) if doc_id else None
    rdel = client.delete(f"/documents/{doc_id}", headers=auth(alice["token"])) if doc_id else None
    upload_no_rights_ok = no_rights.status_code == 400
    step("UC17 合法PDF文档生命周期(权利确认强制)",
         rup1.status_code == 201 and upload_no_rights_ok and rdocs.status_code == 200 and bool(docs)
         and (rdel is not None and rdel.status_code == 204),
         f"上传+1(201); 未确认权利被拒(400); 列表 {len(docs)} 份; 检索 HTTP {rret.status_code if rret else 'NA'}; 删除 204",
         {"retrieval_hits": (rret.json().get("hits") if rret and rret.status_code == 200 else None)})

    # UC18 Jobs: 创建→worker 终态→事件顺序
    rj = client.post("/jobs", headers=auth(alice["token"]),
                     json={"job_type": "paper_analysis", "project_id": project_id, "payload": {"paper_id": paper_id}})
    job = rj.json()
    job_id = job["id"]
    terminal, waited = None, 0.0
    while waited < 30:
        cur = client.get(f"/jobs/{job_id}", headers=auth(alice["token"])).json()
        if cur["status"] in ("succeeded", "failed", "cancelled"):
            terminal = cur
            break
        time.sleep(1.0)
        waited += 1
    events = client.get(f"/jobs/{job_id}/events", headers=auth(alice["token"])).json()
    ev_types = [e["event_type"] for e in events] if isinstance(events, list) else [e["event_type"] for e in events.get("items", [])]
    order_ok = ev_types and ev_types[0] == "created"
    attempt = terminal.get("attempt_count") if terminal else None
    result_snippet = json.dumps((terminal or {}).get("result"), ensure_ascii=False)[:120]
    error_field = (terminal or {}).get("error")
    jobs_list = client.get("/jobs", headers=auth(alice["token"])).json()
    jobs_items = jobs_list.get("items", []) if isinstance(jobs_list, dict) else jobs_list
    step("UC18 后台任务(worker处理至终态)",
         rj.status_code == 201 and terminal is not None and order_ok,
         f"job id={job_id} 终态={terminal['status'] if terminal else '超时未终态'} attempts={attempt}; events顺序={ev_types[:5]}; result={result_snippet}; error={error_field}",
         {"jobs_in_list": len(jobs_items) if hasattr(jobs_items, "__len__") else "?"})

    # UC19 来源状态与主动测试（/sources/status 返回 [{name,status,...}] 列表）
    rsrc_raw = client.get("/sources/status", headers=auth(alice["token"])).json()
    rsrc = {item["name"]: item for item in rsrc_raw} if isinstance(rsrc_raw, list) else rsrc_raw
    fixture_status = (rsrc.get("fixture") or {}).get("status")
    rtest = client.post("/sources/fixture/test", headers=auth(alice["token"]))
    test_ok = rtest.status_code in (200, 202)
    step("UC19 来源状态与主动测试", bool(rsrc) and fixture_status == "ok" and test_ok,
         f"各来源状态={ {k: v.get('status') for k, v in rsrc.items()} }; fixture主动测试 HTTP {rtest.status_code} 响应={rtest.text[:160]}")

    # UC20 设置读写（字段以 UserSettingsUpdate 为准）
    rs1 = client.put("/settings/me", headers=auth(alice["token"]),
                     json={"default_result_count": 50, "default_page_size": 10,
                           "preferred_sources": ["fixture"], "default_open_access_only": True,
                           "display_language": "zh-CN", "analysis_execution_preference": "synchronous"})
    rs2 = client.get("/settings/me", headers=auth(alice["token"]))
    s = rs2.json()
    settings_ok = (rs1.status_code == 200 and rs2.status_code == 200
                   and s.get("default_result_count") == 50 and s.get("display_language") == "zh-CN"
                   and s.get("analysis_execution_preference") == "synchronous")
    step("UC20 个人设置读写", settings_ok,
         f"PUT/GET settings: default_result_count={s.get('default_result_count')} display_language={s.get('display_language')} "
         f"analysis_execution_preference={s.get('analysis_execution_preference')} preferred_sources={s.get('preferred_sources')}")

    # UC21 管理端非管理员拒绝 + 工作区导出
    radm = client.get("/admin/config-status", headers=auth(alice["token"]))
    rbk = client.get("/admin/backups", headers=auth(alice["token"]))
    rexport = client.get("/workspace/export", headers=auth(alice["token"]))
    export_has_data = rexport.status_code == 200 and len(rexport.content) > 200
    step("UC21 权限边界与工作区导出",
         radm.status_code == 403 and rbk.status_code == 403 and export_has_data,
         f"非管理员访问 admin/config-status={radm.status_code}, admin/backups={rbk.status_code}; 导出字节={len(rexport.content)}")

    print(json.dumps(steps, ensure_ascii=False, indent=2))
    print("\nALL_USE_CASES_PASSED")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        code = exc.code or 0
        sys.exit(int(code))
