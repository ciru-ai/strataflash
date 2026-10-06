#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import fs from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import process from "node:process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const LAB_ROOT = process.env.BENCHLAB_ROOT
  || process.env.LLM_BENCHMARKING_LAB_ROOT
  || path.resolve(SCRIPT_DIR, "..");
const HERMES_ROOT = "evidence/ciru/runs/20260929-flash-hermes-unlimited/HermesAgent-20";
const LOOP_WATCHER_V4 = "evidence/ciru/runs/20260929-flash-hermes-unlimited/loop-watcher-v4.py";
const INTEGRITY_AUDIT = "evidence/ciru/runs/20260929-flash-hermes-unlimited/audit_hermes.py";
const BENCHLOCAL_RUNS_ROOT = path.join(LAB_ROOT, ".benchlocal-home/.benchlocal/runs/hermesagent-20");
const BENCH_DOCKER = path.join(LAB_ROOT, "bin/bench-docker");
const SWITCH_MODEL = "/home/benchmark/machine-setup/switch-main-model.sh";
const IMPORTER = "/home/benchmark/.codex/skills/llama-benchmark/scripts/quality_benchmark_store.py";
const DEFAULT_IMAGE = "hermesagent20-verifier:local";
const DEFAULT_MODEL_BASE_URL = process.env.HERMES_AGENT_20_BASE_URL || "http://127.0.0.1:8083/v1";
const DEFAULT_AUTH_MODE = process.env.HERMES_AGENT_20_AUTH_MODE || "bearer";
const DEFAULT_API_KEY = process.env.HERMES_AGENT_20_API_KEY || "local";

const DEFAULT_PROFILES = [
  "CHADROCK3.6-35B-UNCENSORED-MTP-STRIX-LEAN",
  "lfm25-8b-a1b-q8",
  "q36-27b-chadrock-heretic",
  "qwen3.5-9b-q4-km",
  "qwen3.6-27b-mtp-chadrock-rocmfp4-strix-lean",
  "qwen3.6-35b-a3b-ace-saber-rocmfp4-vulkan-d2",
  "qwen3.6-35b-a3b-crown-halo-mtp-dynamic",
  "qwen3.6-35b-a3b-dynamic-strix",
  "qwen3.6-35b-a3b-mtp-chadrock-rocmfp4-strix-lean",
  "qwopus3.6-27b-v2-chadrock-strix-lean-mtp",
  "CHADROCK3.6-35B-UNCENSORED-MTP-ROCM-Q4FAST"
];

const { SCENARIOS, scoreModelResults } = require(path.join(HERMES_ROOT, "dist/lib/benchmark.js"));

function parseArgs(argv) {
  const args = {
    profiles: [],
    scenarios: [],
    image: process.env.HERMES_AGENT_20_IMAGE || DEFAULT_IMAGE,
    runRoot: process.env.HERMES_AGENT_20_RUN_ROOT || BENCHLOCAL_RUNS_ROOT,
    baseUrl: DEFAULT_MODEL_BASE_URL,
    modelId: process.env.HERMES_AGENT_20_MODEL_ID || undefined,
    authMode: DEFAULT_AUTH_MODE,
    apiKey: DEFAULT_API_KEY,
    scenarioTimeoutMs: Number.parseInt(process.env.HERMES_AGENT_20_SCENARIO_TIMEOUT_MS || "1800000", 10),
    fetchRetries: Number.parseInt(process.env.HERMES_AGENT_20_FETCH_RETRIES || "1", 10),
    maxTokens: process.env.HERMES_AGENT_20_MAX_TOKENS
      ? Number.parseInt(process.env.HERMES_AGENT_20_MAX_TOKENS, 10)
      : undefined,
    temperature: process.env.HERMES_AGENT_20_TEMPERATURE
      ? Number.parseFloat(process.env.HERMES_AGENT_20_TEMPERATURE)
      : 0,
    topP: process.env.HERMES_AGENT_20_TOP_P
      ? Number.parseFloat(process.env.HERMES_AGENT_20_TOP_P)
      : undefined,
    topK: process.env.HERMES_AGENT_20_TOP_K
      ? Number.parseInt(process.env.HERMES_AGENT_20_TOP_K, 10)
      : undefined,
    reasoningEffort: process.env.HERMES_AGENT_20_REASONING_EFFORT || undefined,
    requestExtraBody: process.env.HERMES_AGENT_20_REQUEST_EXTRA_BODY
      ? JSON.parse(process.env.HERMES_AGENT_20_REQUEST_EXTRA_BODY)
      : undefined,
    skipSwitch: false,
    skipImport: false,
    verbose: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--profile":
        if (!next) throw new Error("Missing value for --profile");
        args.profiles.push(next);
        index += 1;
        break;
      case "--scenario":
        if (!next) throw new Error("Missing value for --scenario");
        args.scenarios.push(next);
        index += 1;
        break;
      case "--image":
        if (!next) throw new Error("Missing value for --image");
        args.image = next;
        index += 1;
        break;
      case "--run-root":
        if (!next) throw new Error("Missing value for --run-root");
        args.runRoot = next;
        index += 1;
        break;
      case "--base-url":
        if (!next) throw new Error("Missing value for --base-url");
        args.baseUrl = next;
        index += 1;
        break;
      case "--model-id":
        if (!next) throw new Error("Missing value for --model-id");
        args.modelId = next;
        index += 1;
        break;
      case "--auth-mode":
        if (!next) throw new Error("Missing value for --auth-mode");
        args.authMode = next;
        index += 1;
        break;
      case "--api-key":
        if (!next) throw new Error("Missing value for --api-key");
        args.apiKey = next;
        index += 1;
        break;
      case "--scenario-timeout-ms":
        if (!next) throw new Error("Missing value for --scenario-timeout-ms");
        args.scenarioTimeoutMs = Number.parseInt(next, 10);
        if (!Number.isFinite(args.scenarioTimeoutMs) || args.scenarioTimeoutMs <= 0) {
          throw new Error(`Invalid --scenario-timeout-ms value: ${next}`);
        }
        index += 1;
        break;
      case "--fetch-retries":
        if (!next) throw new Error("Missing value for --fetch-retries");
        args.fetchRetries = Number.parseInt(next, 10);
        if (!Number.isFinite(args.fetchRetries) || args.fetchRetries < 0) {
          throw new Error(`Invalid --fetch-retries value: ${next}`);
        }
        index += 1;
        break;
      case "--max-tokens":
        if (!next) throw new Error("Missing value for --max-tokens");
        args.maxTokens = Number.parseInt(next, 10);
        if (!Number.isFinite(args.maxTokens) || args.maxTokens < 65536) {
          throw new Error(`Invalid --max-tokens value: ${next}; use 65536 or omit the flag`);
        }
        index += 1;
        break;
      case "--temperature":
        if (!next) throw new Error("Missing value for --temperature");
        args.temperature = Number.parseFloat(next);
        if (!Number.isFinite(args.temperature) || args.temperature < 0) {
          throw new Error(`Invalid --temperature value: ${next}`);
        }
        index += 1;
        break;
      case "--top-p":
        if (!next) throw new Error("Missing value for --top-p");
        args.topP = Number.parseFloat(next);
        if (!Number.isFinite(args.topP) || args.topP <= 0 || args.topP > 1) {
          throw new Error(`Invalid --top-p value: ${next}`);
        }
        index += 1;
        break;
      case "--top-k":
        if (!next) throw new Error("Missing value for --top-k");
        args.topK = Number.parseInt(next, 10);
        if (!Number.isFinite(args.topK) || args.topK < 0) {
          throw new Error(`Invalid --top-k value: ${next}`);
        }
        index += 1;
        break;
      case "--reasoning-effort":
        if (!next) throw new Error("Missing value for --reasoning-effort");
        args.reasoningEffort = next;
        index += 1;
        break;
      case "--request-extra-body":
        if (!next) throw new Error("Missing value for --request-extra-body");
        args.requestExtraBody = JSON.parse(next);
        if (!args.requestExtraBody || Array.isArray(args.requestExtraBody) || typeof args.requestExtraBody !== "object") {
          throw new Error("--request-extra-body must be a JSON object");
        }
        index += 1;
        break;
      case "--skip-switch":
        args.skipSwitch = true;
        break;
      case "--skip-import":
        args.skipImport = true;
        break;
      case "--verbose":
        args.verbose = true;
        break;
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
      default:
        if (current.startsWith("-")) {
          throw new Error(`Unknown argument: ${current}`);
        }
        args.profiles.push(current);
        break;
    }
  }

  if (args.profiles.length === 0) {
    args.profiles = DEFAULT_PROFILES;
  }

  return args;
}

function printHelp() {
  console.log(`Run HermesAgent-20 against local model profiles.

Usage:
  run-hermesagent20-sweep.mjs
  run-hermesagent20-sweep.mjs --profile qwen3.5-9b-q4-km
  run-hermesagent20-sweep.mjs --scenario HA-01 --skip-switch --profile current-profile

Options:
  --profile <name>   Model profile to run; can be repeated
  --scenario <id>    Scenario id to run; can be repeated; defaults to all 20
  --image <name>     Verifier Docker image; defaults to ${DEFAULT_IMAGE}
  --run-root <dir>   Run output root; defaults to ${BENCHLOCAL_RUNS_ROOT}
  --base-url <url>   OpenAI-compatible endpoint; defaults to ${DEFAULT_MODEL_BASE_URL}
  --model-id <id>    Explicit served/API model id; avoids ambiguous /models discovery
  --auth-mode <mode> bearer or none; defaults to ${DEFAULT_AUTH_MODE}
  --api-key <key>    API key for bearer auth; defaults to local
  --scenario-timeout-ms <ms>
                     Per-scenario timeout; defaults to 1800000
  --fetch-retries <n>
                     Same-scenario retries after verifier fetch failures; defaults to 1
  --max-tokens <n>   Optional generation cap forwarded to Hermes; minimum 65536
  --temperature <n>  Generation temperature; defaults to 0
  --top-p <n>        Optional top-p forwarded to model generation
  --top-k <n>        Optional top-k forwarded to model generation
  --reasoning-effort <level>
                     Optional reasoning effort forwarded to the API
  --request-extra-body <json>
                     Optional JSON object forwarded as OpenAI extra_body
  --skip-switch      Do not switch qwen-main before running
  --skip-import      Do not import finished summaries into the quality DB
  --verbose          Print verifier notes and logs to stdout
`);
}

function slug(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
}

function compactResult(result) {
  const { rawLog, output, ...rest } = result;
  return rest;
}

function nowIso() {
  return new Date().toISOString();
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: { ...process.env, ...(options.env || {}) },
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      if (options.streamStdout) process.stdout.write(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      if (options.streamStderr) process.stderr.write(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ exitCode: code ?? 1, stdout, stderr }));
  });
}

async function requireSuccessful(command, args, options = {}) {
  const result = await runCommand(command, args, options);
  if (result.exitCode !== 0) {
    throw new Error(
      `Command failed: ${[command, ...args].join(" ")}\nexit=${result.exitCode}\nstdout=${result.stdout}\nstderr=${result.stderr}`
    );
  }
  return result;
}

async function allocatePort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("Failed to allocate a local port")));
        return;
      }
      server.close((error) => {
        if (error) reject(error);
        else resolve(address.port);
      });
    });
  });
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHealth(url, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await sleep(1000);
  }
  throw new Error(`Timed out waiting for verifier health: ${url}`);
}

async function startVerifier(image, artifactRoot) {
  const port = await allocatePort();
  const name = `hermesagent20-sweep-${randomUUID().slice(0, 8)}`;
  const resolvedArtifactRoot = path.resolve(artifactRoot);
  await requireSuccessful(BENCH_DOCKER, [
    "run",
    "-d",
    "--rm",
    "--network",
    "host",
    "--name",
    name,
    "-e",
    `PORT=${port}`,
    "-v",
    `${path.join(HERMES_ROOT, "verification")}:/opt/verification`,
    "-v",
    `${LOOP_WATCHER_V4}:/opt/verification/agent-runner.py:ro`,
    "-v",
    `${resolvedArtifactRoot}:${resolvedArtifactRoot}`,
    "--entrypoint",
    "sh",
    image,
    "-lc",
    "(/opt/hermes-venv/bin/pip show pytest >/dev/null 2>&1 || /opt/hermes-venv/bin/pip install -q pytest) && exec node /opt/verification/server.mjs"
  ]);

  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    await waitForHealth(`${baseUrl}/health`);
  } catch (error) {
    const logs = await runCommand(BENCH_DOCKER, ["logs", "--tail", "200", name]);
    await runCommand(BENCH_DOCKER, ["rm", "-f", name]);
    throw new Error(`${error instanceof Error ? error.message : String(error)}\n${logs.stdout || logs.stderr}`);
  }

  return { name, baseUrl };
}

async function stopVerifier(name) {
  await runCommand(BENCH_DOCKER, ["rm", "-f", name]);
}

async function getServedModelId(baseUrl, headers) {
  const response = await fetch(`${baseUrl}/models`, { headers });
  if (!response.ok) {
    throw new Error(`Model endpoint failed: ${response.status} ${response.statusText}`);
  }
  const payload = await response.json();
  const dataId = payload?.data?.find?.((entry) => entry?.id)?.id;
  const modelsId = payload?.models?.find?.((entry) => entry?.model || entry?.name);
  const modelId = dataId || modelsId?.model || modelsId?.name;
  if (!modelId) {
    throw new Error(`No model id found in ${baseUrl}/models`);
  }
  return String(modelId);
}

async function writeJson(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(`${filePath}.tmp`, `${JSON.stringify(value, null, 2)}\n`);
  await fs.rename(`${filePath}.tmp`, filePath);
}

async function appendJsonl(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.appendFile(filePath, `${JSON.stringify(value)}\n`);
}

async function importRun(runDir) {
  await requireSuccessful("python3", [IMPORTER, "import-run", runDir], {
    streamStdout: true,
    streamStderr: true
  });
}

function postJsonNoImplicitTimeout(url, payload, timeoutMs) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const body = JSON.stringify(payload);
    const client = target.protocol === "https:" ? https : http;
    const request = client.request(target, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "content-length": Buffer.byteLength(body)
      }
    }, (response) => {
      const chunks = [];
      response.setEncoding("utf8");
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        resolve({
          ok: response.statusCode >= 200 && response.statusCode < 300,
          status: response.statusCode,
          statusText: response.statusMessage || "",
          text: chunks.join("")
        });
      });
    });

    const timeout = setTimeout(() => {
      const error = new Error(`Scenario timed out after ${timeoutMs} ms.`);
      error.name = "AbortError";
      request.destroy(error);
    }, timeoutMs);
    request.setTimeout(0);
    request.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    request.on("close", () => clearTimeout(timeout));
    request.write(body);
    request.end();
  });
}

function errorNote(error) {
  if (!(error instanceof Error)) return String(error);
  const cause = error.cause instanceof Error
    ? `; cause=${error.cause.name || "Error"}: ${error.cause.message}`
    : "";
  return `${error.name || "Error"}: ${error.message}${cause}`;
}

function isVerifierFetchFailure(result) {
  return result.summary === "Scenario execution failed." && String(result.note || "").includes("fetch failed");
}

async function runScenario(verifier, scenario, model, runId, runDir, verbose, timeoutMs, generation, attempt = 1) {
  const startedAt = nowIso();
  const artifactDir = path.join(runDir, "artifacts", `${scenario.id}-attempt-${attempt}`);
  await fs.mkdir(artifactDir, { recursive: true });
  await fs.chmod(path.dirname(artifactDir), 0o777);
  await fs.chmod(artifactDir, 0o777);
  let result;
  try {
    const response = await postJsonNoImplicitTimeout(
      `${verifier.baseUrl}/run-scenario`,
      {
        scenarioId: scenario.id,
        runId: `${runId}-${scenario.id}-${randomUUID().slice(0, 8)}`,
        model,
        generation,
        artifactDir
      },
      timeoutMs
    );

    if (!response.ok) {
      result = {
        scenarioId: scenario.id,
        status: "fail",
        score: 0,
        summary: `Verifier rejected scenario: ${response.status} ${response.statusText}`,
        note: response.text
      };
    } else {
      result = JSON.parse(response.text);
    }
  } catch (error) {
    result = {
      scenarioId: scenario.id,
      status: "fail",
      score: 0,
      summary: error?.name === "AbortError" ? "Scenario timed out." : "Scenario execution failed.",
      note: errorNote(error),
      timedOut: error?.name === "AbortError"
    };
  }
  // The verifier records the primary agent's calls. Keep these as separate
  // counters; a tool invocation and a model API request are not the same unit.
  const agentResultPath = path.join(artifactDir, "agent-result.json");
  try {
    const agent = JSON.parse(await fs.readFile(agentResultPath, "utf8"));
    result.primaryToolCalls = (agent.toolEvents || []).filter(e => e.phase === "complete").length;
    result.nestedToolCalls = agent.nestedToolCallsCompleted ?? 0;
    result.primaryApiCalls = agent.apiCalls ?? null;
    result.agentCompleted = agent.completed === true;
    result.agentModel = agent.model ?? null;
    if (agent.loopStop) result.loopStop = agent.loopStop;
  } catch (error) {
    result.primaryToolCalls = null;
    result.nestedToolCalls = null;
    result.primaryApiCalls = null;
    result.agentCompleted = null;
    result.agentArtifactError = String(error);
  }
  if (result.loopStop) {
    result.verifierBeforeLoopOverride = {
      status: result.status, score: result.score, summary: result.summary
    };
    result.status = "fail";
    result.score = 0;
    result.summary = "Agent stopped after a repeated tool-action/result cycle.";
    result.note = `${result.note || ""} loop watcher: ${JSON.stringify(result.loopStop)}`.trim();
  }
  const completedAt = nowIso();
  result.timings = {
    ...(result.timings || {}),
    startedAt,
    completedAt,
    durationMs: Date.parse(completedAt) - Date.parse(startedAt)
  };
  result.wallSeconds = result.timings.durationMs / 1000;
  result.attempt = attempt;
  result.artifactDir = result.artifactDir || artifactDir;
  await writeJson(path.join(runDir, "raw", `${scenario.id}.attempt-${attempt}.json`), result);
  await writeJson(path.join(runDir, "raw", `${scenario.id}.json`), result);
  await appendJsonl(path.join(runDir, "events.jsonl"), {
    type: "scenario_result",
    at: completedAt,
    scenarioId: scenario.id,
    attempt,
    status: result.status,
    score: result.score,
    note: result.note
  });

  const label = `[${String(result.status).toUpperCase()}] ${scenario.id} score=${result.score ?? "?"}`;
  console.log(`${label} ${result.summary ?? ""}`.trim());
  if (verbose && result.note) console.log(`note: ${result.note}`);
  if (verbose && result.rawLog) console.log(result.rawLog);

  return compactResult(result);
}

async function runProfile(args, profile, selectedScenarios) {
  const startedAt = nowIso();
  const runId = `${startedAt.replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z")}-hermesagent20-${slug(profile)}`;
  const runDir = path.join(args.runRoot, runId);
  await fs.mkdir(runDir, { recursive: true });
  await fs.mkdir(path.join(runDir, "integrity"), { recursive: true });
  await writeJson(path.join(runDir, "manifest.json"), {
    runId,
    benchPackId: "hermesagent-20",
    profile,
    scenarios: selectedScenarios.map((scenario) => scenario.id),
    startedAt,
    modelBaseUrl: args.baseUrl,
    authMode: args.authMode
  });
  await appendJsonl(path.join(runDir, "events.jsonl"), { type: "run_started", at: startedAt, profile });

  if (!args.skipSwitch) {
    console.log(`\n== Switching to ${profile} ==`);
    await requireSuccessful(SWITCH_MODEL, ["set", profile], {
      streamStdout: true,
      streamStderr: true
    });
  }

  const headers = args.authMode === "bearer" && args.apiKey
    ? { authorization: `Bearer ${args.apiKey}` }
    : {};
  const exposedModel = args.modelId || await getServedModelId(args.baseUrl, headers);
  const model = {
    id: `local-main:${profile}`,
    label: profile,
    provider: "local-main",
    providerModel: exposedModel,
    inferenceBaseUrl: args.baseUrl,
    authMode: args.authMode,
    apiKey: args.authMode === "bearer" ? args.apiKey : undefined,
    exposedModel
  };
  await appendJsonl(path.join(runDir, "events.jsonl"), {
    type: "model_ready",
    at: nowIso(),
    profile,
    exposedModel
  });
  console.log(`Using exposed model id: ${exposedModel}`);

  let verifier = await startVerifier(args.image, runDir);
	  const results = [];
	  try {
	    for (const scenario of selectedScenarios) {
	      let attempt = 1;
        const generation = { temperature: args.temperature };
        if (args.maxTokens) {
          generation.max_tokens = args.maxTokens;
        }
        if (args.topP !== undefined) {
          generation.top_p = args.topP;
        }
        if (args.topK !== undefined) {
          generation.top_k = args.topK;
        }
        if (args.reasoningEffort !== undefined) {
          generation.reasoning_effort = args.reasoningEffort;
        }
        if (args.requestExtraBody !== undefined) {
          generation.extra_body = args.requestExtraBody;
        }
	      let result = await runScenario(verifier, scenario, model, runId, runDir, args.verbose, args.scenarioTimeoutMs, generation, attempt);
	      while (isVerifierFetchFailure(result) && attempt <= args.fetchRetries) {
	        await appendJsonl(path.join(runDir, "events.jsonl"), {
	          type: "scenario_retry_after_fetch_failure",
	          at: nowIso(),
	          scenarioId: scenario.id,
	          failedAttempt: attempt
	        });
	        await stopVerifier(verifier.name);
	        verifier = await startVerifier(args.image, runDir);
	        attempt += 1;
	        result = await runScenario(verifier, scenario, model, runId, runDir, args.verbose, args.scenarioTimeoutMs, generation, attempt);
	      }
	      if (!result.loopStop && !result.timedOut) {
	        await requireSuccessful("python3", [INTEGRITY_AUDIT, result.artifactDir,
	          "--expected-model", exposedModel, "--output-dir", path.join(runDir, "integrity")],
	          {streamStdout: true, streamStderr: true});
	      }
	      results.push(result);
	      const shouldRestartVerifier = result.timedOut
	        || isVerifierFetchFailure(result);
      if (shouldRestartVerifier) {
        await appendJsonl(path.join(runDir, "events.jsonl"), {
          type: result.timedOut ? "verifier_restarted_after_timeout" : "verifier_restarted_after_fetch_failure",
          at: nowIso(),
          scenarioId: scenario.id
        });
        await stopVerifier(verifier.name);
        verifier = await startVerifier(args.image, runDir);
      }
      const partialScore = scoreModelResults(results);
      const partialSummary = {
        runId,
        benchPackId: "hermesagent-20",
        status: "running",
        scenarioCount: selectedScenarios.length,
        startedAt,
        updatedAt: nowIso(),
        completedAt: null,
        modelCount: 1,
        models: [{ id: profile, label: profile, exposedModel }],
        resultsByModel: { [profile]: results },
        scores: { [profile]: partialScore }
      };
      await writeJson(path.join(runDir, "summary.json"), partialSummary);
    }
  } finally {
    await stopVerifier(verifier.name);
  }

  const completedAt = nowIso();
  const score = scoreModelResults(results);
  const summary = {
    runId,
    benchPackId: "hermesagent-20",
    scenarioCount: selectedScenarios.length,
    status: results.length === selectedScenarios.length ? "completed" : "incomplete",
    startedAt,
    completedAt,
    modelCount: 1,
    models: [{ id: profile, label: profile, exposedModel }],
    resultsByModel: { [profile]: results },
    scores: { [profile]: score }
  };
  await writeJson(path.join(runDir, "summary.json"), summary);
  await appendJsonl(path.join(runDir, "events.jsonl"), {
    type: "run_completed",
    at: completedAt,
    profile,
    totalScore: score.totalScore
  });

  console.log(`Completed ${profile}: totalScore=${score.totalScore} runDir=${runDir}`);
  if (!args.skipImport) {
    await importRun(runDir);
  }
  return summary;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const scenarioById = new Map(SCENARIOS.map((scenario) => [scenario.id, scenario]));
  const selectedIds = args.scenarios.length > 0 ? args.scenarios : SCENARIOS.map((scenario) => scenario.id);
  const selectedScenarios = selectedIds.map((id) => {
    const scenario = scenarioById.get(id);
    if (!scenario) throw new Error(`Unknown scenario id: ${id}`);
    return scenario;
  });

  console.log(`HermesAgent-20 sweep: profiles=${args.profiles.length} scenarios=${selectedScenarios.length}`);
  for (const profile of args.profiles) {
    await runProfile(args, profile, selectedScenarios);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
