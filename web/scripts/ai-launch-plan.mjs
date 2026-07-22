import { randomBytes } from "node:crypto";
import path from "node:path";

const LOOPBACK_HOST = "127.0.0.1";
const SERVICE_PORT = 8765;
const E2E_SERVICE_TIMEOUT_MS = "120000";
const POSIX_NEXT_OS_ENVIRONMENT = new Set([
  "HOME",
  "LANG",
  "LC_ALL",
  "LC_CTYPE",
  "PATH",
  "TEMP",
  "TMP",
  "TMPDIR",
]);
const WINDOWS_NEXT_OS_ENVIRONMENT = new Set([
  "LOCALAPPDATA",
  "PATH",
  "PATHEXT",
  "SYSTEMROOT",
  "TEMP",
  "TMP",
  "USERPROFILE",
  "WINDIR",
]);
const NEXT_SERVER_ENVIRONMENT = new Set([
  "TRUSTED_CEO_CODEX_EXECUTABLE",
  "TRUSTED_CEO_CODEX_HOME",
  "TRUSTED_CEO_REPO_ROOT",
  "TRUSTED_CEO_RUN_ALLOWLIST_ROOT",
  "TRUSTED_CEO_RUN_REGISTRY_PATH",
  "TRUSTED_CEO_SERVICE_TIMEOUT_MS",
  "TRUSTED_CEO_WEB_PORT",
  "TRUSTED_CEO_WEB_RUNTIME_ROOT",
]);
export const DEFAULT_REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../..");
const PRODUCTION_PYTHON_MODULE = "trusted_ceo_agent.service.main";
const E2E_PYTHON_MODULE = "trusted_ceo_agent.service.testing_main";

function isUsableInternalToken(token) {
  return (
    typeof token === "string" &&
    token.length <= 256 &&
    /^[A-Za-z0-9_-]+$/u.test(token) &&
    Buffer.from(token, "base64url").byteLength >= 32
  );
}

function trustedWebPort(environment) {
  const configured = environment.TRUSTED_CEO_WEB_PORT ?? "3000";
  if (typeof configured !== "string" || !/^[0-9]+$/u.test(configured)) {
    throw new Error(
      "TRUSTED_CEO_WEB_PORT must be an integer from 1 through 65535.",
    );
  }
  const port = Number(configured);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) {
    throw new Error(
      "TRUSTED_CEO_WEB_PORT must be an integer from 1 through 65535.",
    );
  }
  return String(port);
}

function nextServerEnvironment(environment, platform) {
  const osEnvironment =
    platform === "win32"
      ? WINDOWS_NEXT_OS_ENVIRONMENT
      : POSIX_NEXT_OS_ENVIRONMENT;
  return Object.fromEntries(
    Object.entries(environment).filter(([name, value]) => {
      if (typeof value !== "string") {
        return false;
      }
      const osName = platform === "win32" ? name.toUpperCase() : name;
      return osEnvironment.has(osName) || NEXT_SERVER_ENVIRONMENT.has(name);
    }),
  );
}

function npmInvocation(environment, platform, nodeExecutable) {
  const args = ["--prefix", "web", "run", "dev"];
  if (platform !== "win32") {
    return { args, executable: "npm" };
  }
  const configuredNpmCli = environment.npm_execpath;
  const npmCli =
    typeof configuredNpmCli === "string" &&
    path.isAbsolute(configuredNpmCli) &&
    path.basename(configuredNpmCli).toLowerCase() === "npm-cli.js"
      ? configuredNpmCli
      : path.join(
          path.dirname(nodeExecutable),
          "node_modules",
          "npm",
          "bin",
          "npm-cli.js",
        );
  return {
    args: [npmCli, ...args],
    executable: nodeExecutable,
  };
}

export function loadRootEnvironment(
  repositoryRoot,
  loadEnvFile = (filename) => process.loadEnvFile(filename),
) {
  const filename = path.join(path.resolve(repositoryRoot), ".env.local");
  try {
    loadEnvFile(filename);
    return true;
  } catch (error) {
    if (
      error !== null &&
      typeof error === "object" &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return false;
    }
    throw new Error("Repository environment could not be loaded.");
  }
}

export function buildLaunchPlan({
  environment = process.env,
  internalToken = randomBytes(32).toString("base64url"),
  nodeExecutable = process.execPath,
  platform = process.platform,
  pythonModule = PRODUCTION_PYTHON_MODULE,
  repositoryRoot = DEFAULT_REPOSITORY_ROOT,
  serviceDirectory = "ai-service",
} = {}) {
  if (!isUsableInternalToken(internalToken)) {
    throw new Error("Internal token must contain at least 32 random bytes.");
  }
  if (![PRODUCTION_PYTHON_MODULE, E2E_PYTHON_MODULE].includes(pythonModule)) {
    throw new Error("Python module is not an approved service entrypoint.");
  }
  if (!/^[a-z0-9-]{1,40}$/u.test(serviceDirectory)) {
    throw new Error("Service directory name is invalid.");
  }

  const resolvedRoot = path.resolve(repositoryRoot);
  const serviceRoot = path.join(resolvedRoot, "web", "var", serviceDirectory);
  const serviceUrl = `http://${LOOPBACK_HOST}:${SERVICE_PORT}`;
  const webPort = trustedWebPort(environment);
  const sharedServiceEnvironment = {
    TRUSTED_CEO_INTERNAL_TOKEN: internalToken,
    TRUSTED_CEO_SERVICE_HOST: LOOPBACK_HOST,
    TRUSTED_CEO_SERVICE_PORT: String(SERVICE_PORT),
  };
  const nextEnvironment = {
    ...nextServerEnvironment(environment, platform),
    ...sharedServiceEnvironment,
    ...(pythonModule === E2E_PYTHON_MODULE
      ? { TRUSTED_CEO_SERVICE_TIMEOUT_MS: E2E_SERVICE_TIMEOUT_MS }
      : {}),
    HOSTNAME: LOOPBACK_HOST,
    PORT: webPort,
    TRUSTED_CEO_SERVICE_URL: serviceUrl,
    TRUSTED_CEO_WEB_PORT: webPort,
  };
  const pluginPythonPath = path.join(
    resolvedRoot,
    "plugin",
    "trusted-ceo-agent",
  );
  const inheritedPythonPath = environment.PYTHONPATH;
  const pythonEnvironment = {
    ...environment,
    ...sharedServiceEnvironment,
    PYTHONPATH:
      typeof inheritedPythonPath === "string" && inheritedPythonPath.length > 0
        ? `${pluginPythonPath}${path.delimiter}${inheritedPythonPath}`
        : pluginPythonPath,
    TRUSTED_CEO_SERVICE_ROOT: serviceRoot,
  };

  const childOptions = (env) => ({
    cwd: resolvedRoot,
    detached: platform !== "win32",
    env,
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  const nextInvocation = npmInvocation(
    environment,
    platform,
    nodeExecutable,
  );

  return {
    healthHeaders: {
      "X-Trusted-Ceo-Internal-Token": internalToken,
    },
    healthUrl: `${serviceUrl}/health`,
    internalToken,
    next: {
      ...nextInvocation,
      options: childOptions(nextEnvironment),
    },
    python: {
      args: [
        "run",
        "--project",
        "plugin/trusted-ceo-agent",
        "--frozen",
        "python",
        "-m",
        pythonModule,
      ],
      executable: "uv",
      options: childOptions(pythonEnvironment),
    },
    serviceRoot,
  };
}
