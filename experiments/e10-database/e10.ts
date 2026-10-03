// E10: an AI-XF bundle as a department database.
//
// Loads three real bundles into a throwaway Postgres (concepts + append-only
// events), exports them back, runs concurrent writers under three
// concurrency policies, builds CQRS read models, and swaps a blue read model
// for a green one while readers keep reading. Exploratory: no plan with pass
// criteria preceded it. See e10-results.md.
//
// Usage: bun e10.ts <workdir> <postgres-url>     (run.sh starts the database)

import { SQL } from "bun";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { createHash } from "node:crypto";
import { homedir } from "node:os";

const HERE = import.meta.dir;
const REPO = join(HERE, "..", "..");
const VALIDATOR = join(REPO, "tools", "ai-xf-validate.py");
const [WORK, URL] = [process.argv[2], process.argv[3]];
if (!WORK || !URL) throw new Error("usage: bun e10.ts <workdir> <postgres-url>");

const BUNDLES: Record<string, string> = {
  "example-payments": join(REPO, "examples"),
  psychology: join(homedir(), "Documents", "GitHub", "psychology-kb"),
  "ai-concepts": join(homedir(), "Documents", "GitHub", "ai-concepts-kb"),
};
const RESERVED = new Set(["index.md", "log.md"]);
const FM_RE = /^---\n([\s\S]*?)\n---\n?/;
const LOG_WORDS = ["Initialization", "Creation", "Update", "Merge", "Split", "Deprecation", "Contradiction", "Resolution", "Gap"];
const INVERSE: Record<string, string> = {
  "relates-to": "relates-to", "part-of": "has-part", "depends-on": "depended-on-by", references: "referenced-by",
  "derived-from": "source-of", supersedes: "superseded-by", contradicts: "contradicts", supports: "supported-by",
  "merged-into": "merged-from", "split-from": "split-into", imported: "exported-to", "authored-by": "author-of",
  describes: "described-by", depicts: "depicted-in", remediates: "remediated-by", discusses: "discussed-in",
};
for (const [a, b] of Object.entries({ ...INVERSE })) INVERSE[b] = a;

const results: Record<string, unknown> = { ran_at: new Date().toISOString(), bun: Bun.version };
const sql = new SQL({ url: URL, max: 25 });
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const ms = (t0: number) => Math.round((performance.now() - t0) * 10) / 10;
const pct = (xs: number[], p: number) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? Math.round(s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))] * 10) / 10 : 0;
};
const sleep = (n: number) => Bun.sleep(n);
const log = (...a: unknown[]) => console.log("[e10]", ...a);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const n of readdirSync(dir)) {
    if (n === ".git") continue;
    const p = join(dir, n);
    statSync(p).isDirectory() ? out.push(...walk(p)) : out.push(p);
  }
  return out.sort();
}

function splitDoc(raw: string): { fm: Record<string, any>; body: string } {
  const m = raw.match(FM_RE);
  if (!m) return { fm: {}, body: raw };
  return { fm: (Bun.YAML.parse(m[1]) as Record<string, any>) ?? {}, body: raw.slice(m[0].length) };
}

function validate(bundle: string, fed?: string): { passed: boolean; errors: number; warnings: number; messages: string[] } {
  const args = ["python3", VALIDATOR, bundle, "--level", "3", "--json", ...(fed ? ["--federation", fed] : [])];
  const r = Bun.spawnSync(args);
  const d = JSON.parse(r.stdout.toString());
  const errs = d.findings.filter((f: any) => f.severity === "error");
  return { passed: d.passed, errors: errs.length, warnings: d.findings.length - errs.length, messages: d.findings.map((f: any) => `${f.severity}: ${f.message}`) };
}

function writeFederation(dir: string, bundles: Record<string, string>, typesFile = "types-v1.json") {
  mkdirSync(join(dir, "vocab"), { recursive: true });
  cpSync(join(REPO, "experiments", "real-federation", "vocab", "rels-v1.json"), join(dir, "vocab", "rels-v1.json"));
  if (!existsSync(join(dir, "vocab", typesFile)))
    cpSync(join(REPO, "experiments", "real-federation", "vocab", "types-v1.json"), join(dir, "vocab", typesFile));
  const lines = ['ai-xf: "0.4"', "federation: e10", "vocabularies:", `  types: ./vocab/${typesFile}`, "  rels: ./vocab/rels-v1.json", "bundles:"];
  for (const [ns, p] of Object.entries(bundles)) lines.push(`  - namespace: ${ns}`, "    source: path", `    path: ./${relative(dir, p)}`);
  const f = join(dir, `federation-${typesFile.replace(".json", "")}.ai-xf.yaml`);
  writeFileSync(f, lines.join("\n") + "\n");
  return f;
}

// ---------------------------------------------------------------- 1. storage
async function schema() {
  await sql.unsafe(`
    drop schema if exists rm_blue cascade; drop schema if exists rm_green cascade; drop schema if exists serving cascade;
    drop table if exists concepts, events, bundle_files, concepts_seed cascade;
    create table concepts (
      namespace text not null, id text not null, path text not null,
      revision int not null default 1, content_hash text not null,
      raw text not null, frontmatter jsonb not null, body text not null,
      status text not null default 'stable', updated_at timestamptz not null default now(),
      updated_by text, primary key (namespace, id));
    create table events (
      seq bigserial primary key, namespace text not null, concept_id text,
      type text not null, actor text, at timestamptz not null default now(), payload jsonb);
    create index on events (namespace, concept_id);
    create table bundle_files (namespace text, path text, raw text, primary key (namespace, path));`);
}

async function loadBundle(ns: string, root: string) {
  let concepts = 0, historic = 0;
  for (const f of walk(root)) {
    const rel = relative(root, f), raw = readFileSync(f, "utf8"), name = rel.split("/").pop()!;
    if (!f.endsWith(".md") || RESERVED.has(name)) {
      await sql`insert into bundle_files values (${ns}, ${rel}, ${raw})`;
      if (name === "log.md") {
        // The log vocabulary is already an event vocabulary: replay it as history.
        let day = "1970-01-01";
        for (const line of raw.split("\n")) {
          const h = line.match(/^## (\d{4}-\d{2}-\d{2})/);
          if (h) day = h[1];
          const w = line.match(/^\s*[-*]\s+\*\*([A-Za-z]+)\*\*/);
          if (w && LOG_WORDS.includes(w[1])) {
            const cid = line.match(/`([a-z0-9][a-z0-9-]*)`/)?.[1] ?? null;
            await sql`insert into events (namespace, concept_id, type, actor, at, payload)
                      values (${ns}, ${cid}, ${w[1]}, ${"log.md"}, ${day + "T00:00:00Z"}, ${{ line: line.trim() }}::jsonb)`;
            historic++;
          }
        }
      }
      continue;
    }
    const { fm, body } = splitDoc(raw);
    const id = String(fm.id ?? rel), actor = fm.generated?.by ?? null;
    await sql`insert into concepts (namespace, id, path, content_hash, raw, frontmatter, body, status, updated_by)
              values (${ns}, ${id}, ${rel}, ${sha(raw)}, ${raw}, ${fm}::jsonb, ${body}, ${String(fm.status ?? "stable")}, ${actor})`;
    concepts++;
  }
  return { concepts, historic_log_events: historic };
}

// ------------------------------------------------------------- 2. round trip
async function exportBundle(ns: string, out: string, mode: "verbatim" | "reserialised" | "green") {
  rmSync(out, { recursive: true, force: true });
  for (const r of await sql`select path, raw from bundle_files where namespace = ${ns}`) {
    mkdirSync(dirname(join(out, r.path)), { recursive: true });
    writeFileSync(join(out, r.path), r.raw);
  }
  const rows = mode === "green"
    ? await sql`select path, raw, frontmatter, body from rm_green.concepts where namespace = ${ns}`
    : await sql`select path, raw, frontmatter, body from concepts where namespace = ${ns}`;
  for (const r of rows) {
    mkdirSync(dirname(join(out, r.path)), { recursive: true });
    const text = mode === "verbatim" ? r.raw : `---\n${Bun.YAML.stringify(r.frontmatter, null, 2).trimEnd()}\n---\n${r.body}`;
    writeFileSync(join(out, r.path), text);
  }
}

function classify(orig: string, now: string) {
  if (orig === now) return "identical";
  const a = splitDoc(orig), b = splitDoc(now);
  if (a.body !== b.body) return "body changed";
  if (JSON.stringify(a.fm) === JSON.stringify(b.fm)) return "formatting only (same keys, same order)";
  const sortKeys = (v: any): any => Array.isArray(v) ? v.map(sortKeys)
    : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])])) : v;
  if (JSON.stringify(sortKeys(a.fm)) === JSON.stringify(sortKeys(b.fm))) return "key order changed (values equal)";
  return "values changed";
}

async function roundTrip() {
  const out: Record<string, any> = {};
  for (const mode of ["verbatim", "reserialised"] as const) {
    const dir = join(WORK, `export-${mode}`), fedBundles: Record<string, string> = {};
    const tally: Record<string, number> = {};
    let files = 0;
    for (const [ns, root] of Object.entries(BUNDLES)) {
      const dest = join(dir, ns);
      await exportBundle(ns, dest, mode);
      fedBundles[ns] = dest;
      for (const f of walk(join(WORK, "input", ns))) {
        const rel = relative(join(WORK, "input", ns), f);
        const c = classify(readFileSync(f, "utf8"), readFileSync(join(dest, rel), "utf8"));
        tally[c] = (tally[c] ?? 0) + 1;
        files++;
      }
    }
    const fed = writeFederation(dir, fedBundles);
    const v = Object.fromEntries(Object.keys(BUNDLES).map((ns) => {
      const r = validate(fedBundles[ns], fed);
      return [ns, { passed: r.passed, errors: r.errors, warnings: r.warnings }];
    }));
    out[mode] = { files, classes: tally, validation: v };
  }
  // the inputs, validated the same way, as the baseline
  const fed = writeFederation(join(WORK, "input"), Object.fromEntries(Object.keys(BUNDLES).map((ns) => [ns, join(WORK, "input", ns)])));
  out.input_baseline = Object.fromEntries(Object.keys(BUNDLES).map((ns) => {
    const r = validate(join(WORK, "input", ns), fed);
    return [ns, { passed: r.passed, errors: r.errors, warnings: r.warnings }];
  }));
  // one worked example of what re-serialising does to a file
  const sample = (await sql`select raw, frontmatter, body from concepts where namespace = 'example-payments' and id = 'payment-service'`)[0];
  let withComments = 0, flowLists = 0;
  for (const r of await sql`select raw from concepts`) {
    const fmText = r.raw.match(FM_RE)?.[1] ?? "";
    if (/^\s*#/m.test(fmText)) withComments++;
    if (/: \[/.test(fmText)) flowLists++;
  }
  out.lossy_formatting = { concepts_with_yaml_comments: withComments, concepts_with_flow_lists: flowLists };
  out.sample_reserialised_head = `---\n${Bun.YAML.stringify(sample.frontmatter, null, 2)}`.split("\n").slice(0, 12);
  out.sample_original_head = sample.raw.split("\n").slice(0, 12);
  return out;
}

// ------------------------------------------------------------ 3. concurrency
type Mode = "last-write-wins" | "optimistic (revision)" | "pessimistic (FOR UPDATE)";
function zipfPicker(n: number, s = 1.1) {
  const w = Array.from({ length: n }, (_, i) => 1 / Math.pow(i + 1, s));
  const total = w.reduce((a, b) => a + b, 0);
  const cdf: number[] = [];
  w.reduce((acc, x, i) => (cdf[i] = acc + x / total), 0);
  return () => { const r = Math.random(); let lo = 0, hi = n - 1; while (lo < hi) { const m = (lo + hi) >> 1; cdf[m] < r ? (lo = m + 1) : (hi = m); } return lo; };
}

function applyEdit(kind: number, fm: any, body: string, marker: string, other: string) {
  fm = structuredClone(fm);
  if (kind === 0) body = `${body.trimEnd()}\n\n${marker}.\n`;
  else if (kind === 1) fm.tags = [...(fm.tags ?? []), marker];
  else fm.links = [...(fm.links ?? []), { rel: "relates-to", to: other, note: marker }];
  return { fm, body };
}

async function runWriters(mode: Mode, writers: number, edits: number, ids: string[], think: [number, number], projector?: () => Promise<void>) {
  const pick = zipfPicker(ids.length);
  const done: { marker: string; id: string }[] = [];
  const lat: number[] = [];
  let retries = 0, gaveUp = 0;
  const t0 = performance.now();
  const worker = async (w: number) => {
    for (let i = 0; i < edits; i++) {
      const id = ids[pick()], marker = `e10-w${w}-e${i}`, kind = i % 3, other = ids[(w + i) % ids.length];
      const s = performance.now();
      const pause = () => sleep(think[0] + Math.random() * (think[1] - think[0]));
      let ok = false;
      for (let attempt = 0; attempt < 100 && !ok; attempt++) {
        if (mode === "pessimistic (FOR UPDATE)") {
          await sql.begin(async (tx) => {
            const [r] = await tx`select frontmatter, body, revision from concepts where namespace = 'psychology' and id = ${id} for update`;
            await pause();
            const e = applyEdit(kind, r.frontmatter, r.body, marker, other);
            await tx`update concepts set frontmatter = ${e.fm}::jsonb, body = ${e.body}, revision = revision + 1,
                       updated_at = now(), updated_by = ${"human:w" + w} where namespace = 'psychology' and id = ${id}`;
            await tx`insert into events (namespace, concept_id, type, actor, payload) values ('psychology', ${id}, 'Update', ${"human:w" + w}, ${{ marker }}::jsonb)`;
          });
          ok = true;
        } else {
          const [r] = await sql`select frontmatter, body, revision from concepts where namespace = 'psychology' and id = ${id}`;
          await pause();
          const e = applyEdit(kind, r.frontmatter, r.body, marker, other);
          ok = await sql.begin(async (tx) => {
            const upd = mode === "last-write-wins"
              ? await tx`update concepts set frontmatter = ${e.fm}::jsonb, body = ${e.body}, revision = revision + 1,
                          updated_at = now(), updated_by = ${"human:w" + w} where namespace = 'psychology' and id = ${id} returning revision`
              : await tx`update concepts set frontmatter = ${e.fm}::jsonb, body = ${e.body}, revision = revision + 1,
                          updated_at = now(), updated_by = ${"human:w" + w}
                         where namespace = 'psychology' and id = ${id} and revision = ${r.revision} returning revision`;
            if (!upd.length) return false;
            await tx`insert into events (namespace, concept_id, type, actor, payload) values ('psychology', ${id}, 'Update', ${"human:w" + w}, ${{ marker }}::jsonb)`;
            return true;
          });
          if (!ok) retries++;
        }
      }
      if (!ok) { gaveUp++; continue; }
      lat.push(performance.now() - s);
      done.push({ marker, id });
    }
  };
  let projecting = true;
  const proj = projector ? (async () => { while (projecting) { await projector(); await sleep(20); } })() : null;
  await Promise.all(Array.from({ length: writers }, (_, w) => worker(w)));
  projecting = false;
  if (proj) await proj;
  const wall = performance.now() - t0;
  // lost update = an acknowledged edit whose marker is not in the final row
  const final = new Map<string, string>();
  for (const r of await sql`select id, frontmatter::text || body as t from concepts where namespace = 'psychology'`) final.set(r.id, r.t);
  const lost = done.filter((d) => !final.get(d.id)!.includes(d.marker)).length;
  const hottest = pick === undefined ? null : ids[0];
  return {
    mode, writers, edits_each: edits, acknowledged: done.length, lost_updates: lost,
    lost_pct: Math.round((lost / Math.max(1, done.length)) * 1000) / 10, retries, gave_up: gaveUp,
    throughput_per_s: Math.round(done.length / (wall / 1000)), p50_ms: pct(lat, 50), p95_ms: pct(lat, 95), wall_s: Math.round(wall / 100) / 10,
    hottest_concept: hottest,
  };
}

async function resetPsychology() {
  await sql`delete from concepts where namespace = 'psychology'`;
  await sql`insert into concepts select * from concepts_seed`;
  await sql`delete from events where namespace = 'psychology' and actor like 'human:w%'`;
}

function gitDemo() {
  const dir = join(WORK, "git-demo");
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const git = (...a: string[]) => Bun.spawnSync(["git", "-c", "user.email=e10@example.com", "-c", "user.name=e10", ...a], { cwd: dir });
  const base = readFileSync(join(BUNDLES["example-payments"], "concepts", "payment-service.md"), "utf8");
  const scenarios: [string, (s: string) => string, (s: string) => string][] = [
    ["both add a tag to the same flow-style list", (s) => s.replace("tags: [platform, payments]", "tags: [platform, payments, alpha]"),
      (s) => s.replace("tags: [platform, payments]", "tags: [platform, payments, beta]")],
    ["both append a link to the end of the links list", (s) => s.replace("  - rel: superseded-by\n    to: payment-service-v2\n", "  - rel: superseded-by\n    to: payment-service-v2\n  - rel: relates-to\n    to: alpha\n"),
      (s) => s.replace("  - rel: superseded-by\n    to: payment-service-v2\n", "  - rel: superseded-by\n    to: payment-service-v2\n  - rel: relates-to\n    to: beta\n")],
    ["one edits the description, the other the tags (adjacent lines)", (s) => s.replace(/^description: .*$/m, "description: Changed by A."),
      (s) => s.replace("tags: [platform, payments]", "tags: [platform, payments, beta]")],
    ["one edits frontmatter, the other appends to the body", (s) => s.replace("tags: [platform, payments]", "tags: [platform, payments, alpha]"),
      (s) => s.trimEnd() + "\n\nA sentence added by B.\n"],
  ];
  const outcomes: { scenario: string; conflict: boolean }[] = [];
  git("init", "-q", "-b", "main");
  for (const [name, a, b] of scenarios) {
    writeFileSync(join(dir, "payment-service.md"), base);
    git("add", "-A"); git("commit", "-q", "-m", "base", "--allow-empty");
    git("checkout", "-q", "-b", "a"); writeFileSync(join(dir, "payment-service.md"), a(base)); git("commit", "-qam", "a");
    git("checkout", "-q", "main"); git("checkout", "-q", "-b", "b"); writeFileSync(join(dir, "payment-service.md"), b(base)); git("commit", "-qam", "b");
    const m = git("merge", "-q", "a", "-m", "merge");
    outcomes.push({ scenario: name, conflict: m.exitCode !== 0 });
    git("merge", "--abort"); git("checkout", "-q", "main"); git("branch", "-qD", "a", "b");
  }
  return outcomes;
}

// ------------------------------------------------------------------ 4. CQRS
const PROJECTION_SQL = (s: string) => `
  drop schema if exists ${s} cascade; create schema ${s};
  create table ${s}.concepts as select namespace, id, path, raw, frontmatter, body, status,
         frontmatter->>'type' as type, frontmatter->>'title' as title from public.concepts;
  alter table ${s}.concepts add primary key (namespace, id);
  create table ${s}.links as
    select c.namespace, c.id as src, l->>'rel' as rel, l->>'to' as dst, false as inferred
      from public.concepts c, jsonb_array_elements(case when jsonb_typeof(c.frontmatter->'links') = 'array' then c.frontmatter->'links' else '[]'::jsonb end) l;
  create table ${s}.search as select namespace, id,
    setweight(to_tsvector('english', coalesce(frontmatter->>'title', '')), 'A') ||
    setweight(to_tsvector('english', coalesce(frontmatter->>'description', '')), 'B') ||
    setweight(to_tsvector('english', body), 'C') as tsv from public.concepts;
  create index on ${s}.search using gin (tsv);
  create table ${s}.redirects as
    select c.namespace, c.id, (select l->>'to' from jsonb_array_elements(case when jsonb_typeof(c.frontmatter->'links') = 'array' then c.frontmatter->'links' else '[]'::jsonb end) l
                               where l->>'rel' in ('superseded-by', 'merged-into') limit 1) as successor
      from public.concepts c where c.status = 'deprecated';
  create view ${s}.current as
    select c.namespace, c.id, coalesce(r.successor, c.id) as serve_id, c.status = 'deprecated' as retired
      from ${s}.concepts c left join ${s}.redirects r using (namespace, id);`;

async function buildReadModel(schemaName: string, typeMap?: (fm: any) => string | null) {
  const t0 = performance.now();
  await sql.unsafe(PROJECTION_SQL(schemaName));
  // §6.3: synthesise inverse edges
  const inv = Object.entries(INVERSE).map(([a, b]) => `('${a}','${b}')`).join(",");
  await sql.unsafe(`insert into ${schemaName}.links (namespace, src, rel, dst, inferred)
                    select l.namespace, l.dst, coalesce(m.inv, 'relates-to'), l.src, true
                      from ${schemaName}.links l left join (values ${inv}) m(rel, inv) using (rel)
                     where not l.inferred and position('/' in l.dst) = 0`);
  if (typeMap) {
    for (const r of await sql.unsafe(`select namespace, id, frontmatter from ${schemaName}.concepts`)) {
      const t = typeMap(r.frontmatter);
      if (t) {
        const fm = { ...r.frontmatter, type: t };
        await sql.unsafe(`update ${schemaName}.concepts set type = $1, frontmatter = $2::jsonb where namespace = $3 and id = $4`, [t, fm, r.namespace, r.id]);
      }
    }
  }
  const counts = (await sql.unsafe(`select (select count(*) from ${schemaName}.concepts)::int as concepts,
      (select count(*) from ${schemaName}.links where not inferred)::int as declared_links,
      (select count(*) from ${schemaName}.links where inferred)::int as inferred_links,
      (select count(*) from ${schemaName}.redirects)::int as tombstones,
      (select count(*) from ${schemaName}.redirects where successor is not null)::int as redirects`))[0];
  return { ms: ms(t0), ...counts };
}

async function scaleLoad(copies: number) {
  // A department-sized store: the two real bundles copied into `copies` namespaces.
  const t0 = performance.now();
  for (let k = 1; k <= copies; k++) {
    const ns = `dept-${String(k).padStart(2, "0")}`;
    await sql`insert into concepts (namespace, id, path, revision, content_hash, raw, frontmatter, body, status, updated_by)
              select ${ns}, id, path, 1, content_hash, raw, frontmatter, body, status, updated_by
                from concepts where namespace in ('psychology', 'ai-concepts') on conflict do nothing`;
  }
  return { copies, ms: ms(t0), concepts: (await sql`select count(*)::int as n from concepts`)[0].n };
}

// ------------------------------------------------------------------- main
async function main() {
  for (let i = 0; i < 40; i++) { try { await sql`select 1`; break; } catch { await sleep(500); } }
  rmSync(WORK, { recursive: true, force: true });
  for (const [ns, src] of Object.entries(BUNDLES)) cpSync(src, join(WORK, "input", ns), { recursive: true, filter: (p) => !p.includes("/.git") });

  log("1. storage");
  await schema();
  const t0 = performance.now();
  const loaded: Record<string, unknown> = {};
  for (const ns of Object.keys(BUNDLES)) loaded[ns] = await loadBundle(ns, join(WORK, "input", ns));
  await sql`insert into events (namespace, concept_id, type, actor, payload)
            select namespace, id, 'Creation', coalesce(updated_by, 'unknown'), jsonb_build_object('source', 'bundle import') from concepts`;
  results.storage = { loaded, load_ms: ms(t0),
    events: (await sql`select type, count(*)::int as n from events group by type order by n desc`).map((r: any) => [r.type, r.n]) };
  await sql`create table concepts_seed as select * from concepts where namespace = 'psychology'`;

  log("2. round trip");
  results.round_trip = await roundTrip();

  log("3. concurrency");
  const ids = (await sql`select id from concepts where namespace = 'psychology' order by id`).map((r: any) => r.id);
  // rank 1 under the Zipf picker is ids[0]; shuffle so the hot set is arbitrary but fixed
  ids.sort((a: string, b: string) => sha(a).localeCompare(sha(b)));
  const conc: unknown[] = [];
  for (const mode of ["last-write-wins", "optimistic (revision)", "pessimistic (FOR UPDATE)"] as Mode[]) {
    await resetPsychology();
    const r = await runWriters(mode, 50, 200, ids, [0, 4]);
    log(JSON.stringify(r));
    conc.push(r);
  }
  // What the writers did to the format: `raw` is no longer the truth, and the
  // parsed fields, serialised, may no longer be a valid bundle.
  const drift = (await sql`select count(*)::int as n from concepts where namespace = 'psychology' and revision > 1`)[0].n;
  const wdir = join(WORK, "export-after-writers");
  await exportBundle("psychology", join(wdir, "psychology"), "reserialised");
  const wfed = writeFederation(wdir, { psychology: join(wdir, "psychology") });
  const wv = validate(join(wdir, "psychology"), wfed);
  const kinds: Record<string, number> = {};
  for (const m of wv.messages.filter((m) => m.startsWith("error"))) {
    const k = m.includes("not mirrored") ? "typed link not mirrored in body (§6.4)" : m.slice(0, 60);
    kinds[k] = (kinds[k] ?? 0) + 1;
  }
  results.concurrency = { runs: conc, git_merge: gitDemo(),
    after_writers: { concepts_edited_raw_stale: drift, export_errors: wv.errors, error_kinds: kinds },
    note: "50 writers x 200 read-modify-write edits on 102 concepts, Zipf s=1.1, 0-4 ms think time between read and write, pool of 25 connections" };

  log("4. CQRS");
  await resetPsychology();
  const blueSmall = await buildReadModel("rm_blue");
  const scale = await scaleLoad(50);
  const blueScaled = await buildReadModel("rm_blue");
  // incremental: a projector applies new events to the search and link read models while writers run
  let last = (await sql`select coalesce(max(seq), 0)::int as s from events`)[0].s;
  const lags: number[] = [];
  const projector = async () => {
    const evs = await sql`select seq, namespace, concept_id, extract(epoch from at) * 1000 as at_ms from events where seq > ${last} order by seq limit 500`;
    if (!evs.length) return;
    const touched = [...new Set(evs.map((e: any) => `${e.namespace}\u0000${e.concept_id}`))].map((k) => k.split("\u0000"));
    for (const [ns, id] of touched) {
      await sql.begin(async (tx) => {
        await tx`delete from rm_blue.search where namespace = ${ns} and id = ${id}`;
        await tx.unsafe(`insert into rm_blue.search select namespace, id,
            setweight(to_tsvector('english', coalesce(frontmatter->>'title', '')), 'A') ||
            setweight(to_tsvector('english', coalesce(frontmatter->>'description', '')), 'B') ||
            setweight(to_tsvector('english', body), 'C') from public.concepts where namespace = $1 and id = $2`, [ns, id]);
        await tx`delete from rm_blue.links where namespace = ${ns} and (src = ${id} or (inferred and dst = ${id}))`;
        await tx.unsafe(`insert into rm_blue.links select c.namespace, c.id, l->>'rel', l->>'to', false from public.concepts c,
            jsonb_array_elements(case when jsonb_typeof(c.frontmatter->'links') = 'array' then c.frontmatter->'links' else '[]'::jsonb end) l
            where c.namespace = $1 and c.id = $2`, [ns, id]);
      });
    }
    const now = Date.now();
    for (const e of evs) lags.push(now - Number(e.at_ms));
    last = evs[evs.length - 1].seq;
  };
  const during = await runWriters("optimistic (revision)", 20, 100, ids, [0, 4], projector);
  await projector();
  const searchCheck = (await sql`select count(*)::int as n from rm_blue.search s where s.namespace = 'psychology' and s.tsv @@ to_tsquery('english', 'e10')`)[0].n;
  results.cqrs = { rebuild_172: blueSmall, scaled_load: scale, rebuild_scaled: blueScaled,
    incremental: { writers: during, events_projected: lags.length, lag_p50_ms: pct(lags, 50), lag_p95_ms: pct(lags, 95), lag_max_ms: pct(lags, 100),
                   concepts_findable_by_new_text: searchCheck } };

  log("5. blue/green");
  await resetPsychology();   // a clean source: the writers' links are measured in section 3
  await buildReadModel("rm_blue");
  // green: refine `type` from the vault's conceptType (E8's type collapse), validated before it serves
  const titleCase = (s: string) => s.replace(/(^|-)(\w)/g, (_m, _d, c) => c.toUpperCase());
  const green = await buildReadModel("rm_green", (fm) => (fm.conceptType && fm.type === "Concept" ? titleCase(String(fm.conceptType)) : null));
  const newTypes = (await sql`select distinct type from rm_green.concepts where namespace in ('psychology','ai-concepts') order by 1`).map((r: any) => r.type);
  // gate: export green and validate, first against the old vocabulary, then the expanded one
  const gdir = join(WORK, "export-green"), gb: Record<string, string> = {};
  for (const ns of Object.keys(BUNDLES)) { await exportBundle(ns, join(gdir, ns), "green"); gb[ns] = join(gdir, ns); }
  const fedOld = writeFederation(gdir, gb);
  const typesV2 = JSON.parse(readFileSync(join(REPO, "experiments", "real-federation", "vocab", "types-v1.json"), "utf8"));
  for (const t of newTypes) if (!typesV2.values.some((v: any) => v.name === t)) typesV2.values.push({ name: t, definition: `A ${t.toLowerCase()} (refined from conceptType).` });
  writeFileSync(join(gdir, "vocab", "types-v2.json"), JSON.stringify({ ...typesV2, version: 2 }, null, 2));
  const fedNew = writeFederation(gdir, gb, "types-v2.json");
  const gate = (fed: string) => Object.fromEntries(Object.keys(gb).map((ns) => {
    const r = validate(gb[ns], fed);
    return [ns, { passed: r.passed, errors: r.errors, warnings: r.warnings, type_vocab_warnings: r.messages.filter((m) => m.includes("federation vocabulary") && m.includes("type")).length }];
  }));
  const gateOld = gate(fedOld), gateNew = gate(fedNew);
  // swap while readers read through a stable name
  await sql.unsafe(`create schema serving; create view serving.concepts as select * from rm_blue.concepts;`);
  let reading = true, reads = 0, readErrors = 0;
  const readLat: number[] = [];
  const reader = async () => {
    while (reading) {
      const s = performance.now();
      try { await sql`select type, count(*) from serving.concepts group by type`; reads++; readLat.push(performance.now() - s); } catch { readErrors++; }
    }
  };
  const readers = Array.from({ length: 10 }, reader);
  await sleep(300);
  const before = (await sql`select count(distinct type)::int as n from serving.concepts`)[0].n;
  const s0 = performance.now();
  await sql.begin(async (tx) => { await tx.unsafe(`create or replace view serving.concepts as select * from rm_green.concepts`); });
  const swapMs = ms(s0);
  await sleep(300);
  const after = (await sql`select count(distinct type)::int as n from serving.concepts`)[0].n;
  const r0 = performance.now();
  await sql.unsafe(`create or replace view serving.concepts as select * from rm_blue.concepts`);
  const rollbackMs = ms(r0);
  await sleep(200);
  reading = false;
  await Promise.all(readers);
  results.blue_green = { green_build: green, new_types: newTypes,
    gate_with_old_vocabulary: gateOld, gate_with_expanded_vocabulary: gateNew,
    swap: { ms: swapMs, rollback_ms: rollbackMs, reads, reader_errors: readErrors, read_p50_ms: pct(readLat, 50), read_p99_ms: pct(readLat, 99), read_max_ms: pct(readLat, 100),
            distinct_types_before: before, distinct_types_after: after } };

  writeFileSync(join(HERE, "results.json"), JSON.stringify(results, null, 2) + "\n");
  log("wrote results.json");
  await sql.close();
}

await main();
