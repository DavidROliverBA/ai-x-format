#!/usr/bin/env python3
"""E11 converters: a Word/SharePoint library and a Confluence space, each into
an AI-XF bundle two ways.

  naive   MarkItDown straight to markdown, frontmatter `type` and `title` only.
          What a lift-and-shift export produces.
  mapped  The same body text, plus every piece of source metadata mapped onto
          AI-XF/OKF fields: stable ids from the system's own id (never the
          title, which changes), trust from approval events, provenance from
          the original URL, version history into log.md, internal links
          resolved to concepts, media extracted with hashes, comments kept as
          open questions, tracked changes kept visible, restricted pages
          withheld.

Usage: python3 convert.py <corpus-dir> <out-dir>
       (needs markitdown[docx], python-docx >= 1.2, pyyaml)
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import yaml
from docx import Document
from markitdown import MarkItDown

CORPUS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
MIGRATED_AT = "2026-10-03T00:00:00Z"        # fixed, so re-runs are byte-identical
PRODUCER = "e11-migrate/0.1"
STALE_DAYS = 365
MD = MarkItDown()
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
AC, RI = "http://atlassian.com/content", "http://atlassian.com/resource/identifier"
LABEL_TYPES = {"runbook": "Runbook", "policy": "Policy", "data-asset": "DataAsset", "system": "System"}
CORE_RELS = {"references": "referenced-by", "part-of": "has-part", "authored-by": "author-of"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def ts(s: str) -> str:
    return s if s.endswith("Z") else s + "Z"


def plus_days(s: str, n: int) -> str:
    return (datetime.fromisoformat(s.replace("Z", "+00:00")) + timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def frontmatter(fm: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000).strip() + "\n---\n\n" + body.strip() + "\n"


def related(links: list[dict], labels: dict[str, str], here: str) -> str:
    """The §6.4 mirror: one plain body link per typed link."""
    if not links:
        return ""
    out = ["", "## Related", ""]
    for ln in links:
        target = ln["to"]
        rel_path = f"../people/{target}.md" if target.startswith("person-") else f"./{target}.md"
        if here == "people":
            rel_path = rel_path.replace("../people/", "./").replace("./doc-", "../concepts/doc-").replace("./page-", "../concepts/page-")
        out.append(f"- {ln['rel']}: [{labels.get(target, target)}]({rel_path})")
    return "\n".join(out) + "\n"


class Bundle:
    def __init__(self, root: Path, name: str, namespace: str):
        self.root, self.name, self.namespace = root, name, namespace
        self.concepts: list[tuple[str, str, dict, str]] = []   # (dir, id, fm, body)
        self.log: dict[str, list[str]] = {}
        self.people: dict[str, str] = {}
        self.media: dict[str, bytes] = {}
        self.map: dict[str, str] = {}

    def person(self, name: str) -> str:
        pid = "person-" + slug(name)
        self.people[pid] = name
        return pid

    def entry(self, when: str, word: str, cid: str, text: str) -> None:
        self.log.setdefault(when[:10], []).append(f"- **{word}** — `{cid}`: {text}.")

    def write(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        labels = {cid: fm.get("title", cid) for _, cid, fm, _ in self.concepts}
        labels.update(self.people)
        for pid, name in sorted(self.people.items()):
            fm = {"type": "Person", "id": pid, "title": name, "status": "stable",
                  "generated": {"by": PRODUCER, "at": MIGRATED_AT}}
            self.concepts.append(("people", pid, fm, f"# {name}\n\nAuthor or reviewer of migrated content."))
        types, rels = set(), set()
        for d, cid, fm, body in self.concepts:
            types.add(fm["type"])
            for ln in fm.get("links", []):
                rels.add(ln["rel"])
            path = self.root / d / f"{cid}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(frontmatter(fm, body.rstrip() + "\n" + related(fm.get("links", []), labels, d)), encoding="utf-8")
        for name, data in self.media.items():
            (self.root / "assets").mkdir(parents=True, exist_ok=True)
            (self.root / "assets" / name).write_bytes(data)
        (self.root / "vocab").mkdir(parents=True, exist_ok=True)
        (self.root / "vocab" / "types.json").write_text(json.dumps(
            {"version": 1, "values": [{"name": t, "definition": f"Migrated {t}."} for t in sorted(types)]}, indent=2))
        allrels = sorted(rels | {CORE_RELS[r] for r in rels if r in CORE_RELS})
        (self.root / "vocab" / "rels.json").write_text(json.dumps(
            {"version": 1, "values": [{"name": r, "definition": f"AI-XF core rel {r}."} for r in allrels]}, indent=2))
        idx = [f"# {self.name}", "", "## Concepts", ""]
        idx += [f"- [{fm.get('title', cid)}](./{d}/{cid}.md)" for d, cid, fm, _ in self.concepts if d == "concepts"]
        idx += ["", "## People", ""]
        idx += [f"- [{fm.get('title', cid)}](./{d}/{cid}.md)" for d, cid, fm, _ in self.concepts if d == "people"]
        (self.root / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
        self.entry(MIGRATED_AT, "Initialization", self.namespace, f"migrated by {PRODUCER}")
        log = ["# Changelog", ""]
        for day in sorted(self.log, reverse=True):
            log += [f"## {day}", ""] + self.log[day] + [""]
        (self.root / "log.md").write_text("\n".join(log), encoding="utf-8")
        man = {"ai-xf": "0.4", "name": self.name, "namespace": self.namespace,
               "description": f"Migrated into AI-XF by {PRODUCER} (experiment E11).", "producer": PRODUCER,
               "generated": MIGRATED_AT, "conformance": 3,
               "vocabularies": {"types": "vocab/types.json", "rels": "vocab/rels.json"},
               "counts": {"concepts": sum(1 for c in self.concepts if c[0] == "concepts"), "people": len(self.people)}}
        (self.root / "manifest.ai-xf.yaml").write_text(yaml.safe_dump(man, sort_keys=False), encoding="utf-8")
        (self.root.parent / f"{self.root.name}.map.json").write_text(json.dumps(self.map, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- naive

def naive() -> None:
    for src, glob in (("word", "word/**/*.docx"), ("confluence", "confluence/*.storage.xhtml")):
        root = OUT / f"naive-{src}"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        m = {}
        for f in sorted(CORPUS.glob(glob)):
            if src == "word":
                title, text = f.stem, MD.convert(str(f)).text_content
            else:
                title = json.loads(f.with_name(f.name.replace(".storage.xhtml", ".json")).read_text())["title"]
                with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as tmp:
                    tmp.write(f.read_text())
                text = MD.convert(tmp.name).text_content
            name = slug(title) + ".md"
            (root / name).write_text(f"---\ntype: Document\ntitle: {title}\n---\n\n{text.strip()}\n", encoding="utf-8")
            m[title] = name
        (OUT / f"naive-{src}.map.json").write_text(json.dumps(m, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- mapped: Word

def docx_internals(path: Path) -> tuple[list[dict], list[dict], list[tuple[str, bytes]]]:
    """Tracked changes, comments and embedded images, read from the package."""
    d = Document(str(path))
    changes = []
    for el in d.element.body.iter():
        if el.tag in (W + "ins", W + "del"):
            text = "".join(t.text or "" for t in el.iter() if t.tag in (W + "t", W + "delText")).strip()
            changes.append({"kind": "inserted" if el.tag == W + "ins" else "deleted", "text": text,
                            "author": el.get(W + "author"), "at": el.get(W + "date")})
    comments = [{"author": c.author, "text": c.text.strip()} for c in d.comments]
    images = [(rel.target_ref.split("/")[-1], rel.target_part.blob) for rel in d.part.rels.values()
              if "image" in rel.reltype]
    return changes, comments, images


def mapped_word() -> None:
    b = Bundle(OUT / "mapped-word", "Northwind Pay: payments platform library", "sharepoint-payments-platform")
    docs = []
    for f in sorted(CORPUS.glob("word/**/*.docx")):
        side = json.loads(f.with_name(f.stem + ".sharepoint.json").read_text())
        docs.append((f, side, "doc-" + slug(side["documentId"])))
    url_to_id = {unquote(side["url"]): cid for _, side, cid in docs}
    for f, side, cid in docs:
        cp = Document(str(f)).core_properties
        title = cp.title
        b.map[title] = f"concepts/{cid}.md"
        text = MD.convert(str(f)).text_content.strip()
        lines = text.split("\n")
        if lines and lines[0].strip() == title.replace(":", ":"):
            lines[0] = f"# {title}"
        elif lines and lines[0].strip() and not lines[0].startswith("#"):
            lines[0] = f"# {lines[0].strip()}"          # the Title style is not a heading to MarkItDown
        text = "\n".join(lines)
        links = []
        for url in sorted(set(re.findall(r"\]\((https://[^)]+)\)", text))):
            target = url_to_id.get(unquote(url))
            if target:
                text = text.replace(f"]({url})", f"](./{target}.md)")
                links.append({"rel": "references", "to": target})
        changes, comments, images = docx_internals(f)
        media = []
        for name, data in images:
            h = hashlib.sha256(data).hexdigest()
            asset = f"{h[:12]}{Path(name).suffix}"
            b.media[asset] = data
            media.append({"uri": f"../assets/{asset}", "hash": f"sha256:{h}", "title": f"{title}: {name}"})
            text = text.replace("![](data:image/png;base64...)", f"![{title}](../assets/{asset})", 1)
        if comments:
            text += "\n\n## Open review comments (migrated from Word)\n\n" + "\n".join(
                f"- {c['author']}: {c['text']}" for c in comments)
        if changes:
            text += ("\n\n## Pending tracked changes (migrated from Word)\n\nThe text above shows every change as "
                     "accepted. None had been accepted in the source document.\n\n") + "\n".join(
                f"- {c['kind'].capitalize()} by {c['author']}, {c['at'][:10]}: \"{c['text']}\"" for c in changes)
        author, modby = b.person(cp.author), b.person(cp.last_modified_by)
        links.append({"rel": "authored-by", "to": author})
        modified = ts(side["versions"][-1]["modified"])
        ap = side["approval"]
        fm = {"type": side["contentType"], "id": cid, "title": title,
              "description": cp.subject, "aliases": [title, slug(title)],
              "tags": sorted({slug(t) for t in side["managedMetadata"]} | {slug(k) for k in cp.keywords.split(";")}),
              "generated": {"by": f"human:{modby[7:]}", "at": modified}}
        if ap["status"] == "Approved":
            fm["verified"] = [{"by": f"human:{slug(ap['by'])}", "at": ap["at"]}]
            b.person(ap["by"])
        fm["status"] = "stable" if ap["status"] == "Approved" else "draft"
        fm["stale_after"] = plus_days(modified, STALE_DAYS)
        fm["sources"] = [{"id": "sharepoint", "resource": side["url"], "title": f"{title} (SharePoint, version "
                          f"{side['versions'][-1]['version']})", "last_modified": modified}]
        fm["provenance"] = {"source": "secondary"}
        fm["links"] = links
        if media:
            fm["media"] = media
        fm["sharepoint"] = {"document_id": side["documentId"], "content_type": side["contentType"],
                            "library_path": f"{side['library']}/{side['folder']}", "approval": ap["status"],
                            "version": side["versions"][-1]["version"], "permissions": side["permissions"],
                            "open_comments": len(comments), "pending_changes": len(changes)}
        b.concepts.append(("concepts", cid, fm, text))
        for i, v in enumerate(side["versions"]):
            b.entry(ts(v["modified"]), "Creation" if i == 0 else "Update", cid,
                    f"{v['comment']} by {v['modifiedBy']} (SharePoint version {v['version']})")
        for c in comments:
            b.entry(MIGRATED_AT, "Gap", cid, f"open review comment from {c['author']}: {c['text']}")
    b.write()


# ------------------------------------------------------------------- mapped: Confluence

def mapped_confluence() -> None:
    b = Bundle(OUT / "mapped-confluence", "Northwind Pay: Confluence space NWP", "confluence-nwp")
    users = json.loads((CORPUS / "confluence" / "users.json").read_text())
    pages = {}
    for f in sorted(CORPUS.glob("confluence/*.json")):
        if f.name == "users.json":
            continue
        meta = json.loads(f.read_text())
        pages[meta["id"]] = (meta, f.with_name(f"{meta['id']}.storage.xhtml").read_text())
    by_title = {m["title"]: pid for pid, (m, _) in pages.items()}
    withheld_ids = {pid for pid, (m, _) in pages.items() if m["restrictions"]}
    stats = {"withheld_pages": len(withheld_ids), "withheld_links": 0}

    for pid, (meta, xhtml) in sorted(pages.items()):
        if pid in withheld_ids:
            continue                                   # restricted: never exported, not even its title
        cid = f"page-{pid}"
        b.map[meta["title"]] = f"concepts/{cid}.md"
        root = ET.fromstring(f'<root xmlns:ac="{AC}" xmlns:ri="{RI}">{xhtml}</root>')
        links, media, props = [], [], {}

        def render(el) -> str:
            tag = el.tag
            inner = lambda: (el.text or "") + "".join(render(c) + (c.tail or "") for c in el)
            if tag == f"{{{AC}}}structured-macro":
                name = el.get(f"{{{AC}}}name")
                params = {p.get(f"{{{AC}}}name"): (p.text or "") for p in el.findall(f"{{{AC}}}parameter")}
                rich = el.find(f"{{{AC}}}rich-text-body")
                plain = el.find(f"{{{AC}}}plain-text-body")
                body = "" if rich is None else (rich.text or "") + "".join(render(c) + (c.tail or "") for c in rich)
                if name in ("info", "warning", "note", "tip"):
                    return f"<blockquote><p><strong>{name.capitalize()}:</strong></p>{body}</blockquote>"
                if name == "code":
                    code = (plain.text or "") if plain is not None else ""
                    return f"<pre><code>{code.replace('&', '&amp;').replace('<', '&lt;')}</code></pre>"
                if name == "expand":
                    return f"<p><strong>{params.get('title', 'Details')}</strong></p>{body}"
                if name == "jira":
                    k = params.get("key", "")
                    return f'<p><a href="https://jira.example.com/browse/{k}">{k}</a></p>'
                if name == "details":
                    for row in rich.iter("tr"):
                        cells = [("".join(c.itertext())).strip() for c in row]
                        if len(cells) == 2:
                            props[slug(cells[0])] = cells[1]
                    return body
                if name == "toc":
                    return ""                          # regenerable from headings
                return body
            if tag == f"{{{AC}}}link":
                page, user, att = el.find(f"{{{RI}}}page"), el.find(f"{{{RI}}}user"), el.find(f"{{{RI}}}attachment")
                label = el.find(f"{{{AC}}}plain-text-link-body")
                text = (label.text if label is not None else "") or ""
                if page is not None:
                    tid = by_title.get(page.get(f"{{{RI}}}content-title"))
                    if tid in withheld_ids:
                        stats["withheld_links"] += 1
                        return "<em>a page withheld from this export</em>"
                    if tid:
                        links.append({"rel": "references", "to": f"page-{tid}"})
                        return f'<a href="./page-{tid}.md">{text or pages[tid][0]["title"]}</a>'
                    return text
                if user is not None:
                    name = users.get(user.get(f"{{{RI}}}account-id"), "a former user")
                    pidp = b.person(name)
                    links.append({"rel": "references", "to": pidp})
                    return f'<a href="../people/{pidp}.md">{name}</a>'
                if att is not None:
                    fn = att.get(f"{{{RI}}}filename")
                    url = f"https://example.atlassian.net/wiki/download/attachments/{pid}/{fn}"
                    media.append({"uri": url, "title": fn})
                    return f'<a href="{url}">{fn}</a>'
            if tag == f"{{{AC}}}image":
                att = el.find(f"{{{RI}}}attachment")
                fn = att.get(f"{{{RI}}}filename") if att is not None else "image"
                url = f"https://example.atlassian.net/wiki/download/attachments/{pid}/{fn}"
                media.append({"uri": url, "title": fn})
                return f'<p><a href="{url}">{fn}</a> (attachment, not migrated)</p>'
            if tag in (f"{{{AC}}}parameter", f"{{{AC}}}plain-text-link-body"):
                return ""
            attrs = ""
            return f"<{tag}{attrs}>{inner()}</{tag}>" if tag != "root" else inner()

        html = render(root)
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as tmp:
            tmp.write(f"<html><body>{html}</body></html>")
        body = f"# {meta['title']}\n\n" + MD.convert(tmp.name).text_content.strip()
        versions = meta["history"]["versions"]
        last = versions[-1]
        creator = b.person(meta["history"]["createdBy"]["displayName"])
        links.append({"rel": "authored-by", "to": creator})
        if meta["ancestors"]:
            parent = meta["ancestors"][-1]["id"]
            if parent not in withheld_ids:
                links.append({"rel": "part-of", "to": f"page-{parent}"})
        seen, uniq = set(), []
        for ln in links:
            if (ln["rel"], ln["to"]) not in seen:
                seen.add((ln["rel"], ln["to"]))
                uniq.append(ln)
        labels = [l["name"] for l in meta["metadata"]["labels"]["results"]]
        state = meta.get("contentState") or {}
        fm = {"type": next((LABEL_TYPES[l] for l in labels if l in LABEL_TYPES), "Concept"), "id": cid,
              "title": meta["title"], "aliases": [meta["title"], slug(meta["title"])], "tags": labels,
              "generated": {"by": f"human:{slug(last['by']['displayName'])}", "at": ts(last["when"])}}
        if state.get("name") == "verified":
            fm["verified"] = [{"by": f"human:{slug(users[state['by']])}", "at": state["at"]}]
        fm["status"] = "draft" if state.get("name") in ("rough draft", "in progress") else "stable"
        fm["stale_after"] = plus_days(ts(last["when"]), STALE_DAYS)
        page_url = meta["_links"]["base"] + meta["_links"]["webui"]
        fm["sources"] = [{"id": "confluence", "resource": page_url,
                          "title": f"{meta['title']} (Confluence, version {meta['version']['number']})",
                          "last_modified": ts(last["when"])}]
        fm["provenance"] = {"source": "secondary"}
        fm["links"] = uniq
        if media:
            fm["media"] = media
        fm["confluence"] = {"page_id": pid, "space": meta["space"]["key"], "version": meta["version"]["number"],
                            **({"properties": props} if props else {})}
        b.concepts.append(("concepts", cid, fm, body))
        for i, v in enumerate(versions):
            b.entry(ts(v["when"]), "Creation" if i == 0 else "Update", cid,
                    f"{v['message']} by {v['by']['displayName']} (Confluence version {v['number']})")
    b.write()
    (OUT / "mapped-confluence.stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    naive()
    mapped_word()
    mapped_confluence()
    print(f"bundles written to {OUT}")
