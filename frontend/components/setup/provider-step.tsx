'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, CircleNotch, X } from '@phosphor-icons/react/dist/ssr';
import type { SetupData } from './setup-wizard';

interface ProviderStepProps {
  data: SetupData;
  updateData: (updates: Partial<SetupData>) => void;
}

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

const CLAUDE_CLI_MODELS = [
  { value: 'claude-haiku-4-5', label: 'Claude Haiku — fast, efficient' },
  { value: 'claude-sonnet-4-5', label: 'Claude Sonnet — balanced' },
  { value: 'claude-opus-4-5', label: 'Claude Opus — most capable' },
];

const GEMINI_CLI_MODELS = [
  { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash — fast' },
  { value: 'gemini-2.0-flash-thinking-exp', label: 'Gemini 2.0 Flash Thinking — reasoning' },
  { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro — large context' },
];

interface ProviderCardProps {
  id: SetupData['llm_provider'];
  selected: boolean;
  onClick: () => void;
  name: string;
  desc: string;
  badge?: 'free' | 'api' | 'local';
}

function ProviderCard({ id: _id, selected, onClick, name, desc, badge }: ProviderCardProps) {
  const badgeLabel = badge === 'free' ? 'FREE' : badge === 'api' ? 'API KEY' : badge === 'local' ? 'LOCAL' : null;
  const badgeColor =
    badge === 'free'
      ? 'bg-emerald-500/15 text-emerald-400'
      : badge === 'api'
        ? 'bg-blue-500/15 text-blue-400'
        : 'bg-amber-500/15 text-amber-400';

  return (
    <button
      onClick={onClick}
      className={`rounded-xl border p-4 text-left transition-all ${
        selected
          ? 'border-primary bg-primary/8 shadow-sm'
          : 'border-input hover:border-muted-foreground/60 hover:bg-muted/30'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium text-sm leading-tight">{name}</div>
        {badgeLabel && (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badgeColor}`}>
            {badgeLabel}
          </span>
        )}
      </div>
      <div className="text-muted-foreground mt-1 text-xs leading-snug">{desc}</div>
    </button>
  );
}

function StatusIcon({ status }: { status: TestStatus }) {
  switch (status) {
    case 'testing':
      return <CircleNotch className="h-4 w-4 animate-spin text-blue-500" />;
    case 'success':
      return <Check className="h-4 w-4 text-green-500" weight="bold" />;
    case 'error':
      return <X className="h-4 w-4 text-red-500" weight="bold" />;
    default:
      return null;
  }
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="col-span-2 mt-1 flex items-center gap-2">
      <span className="text-muted-foreground text-[11px] font-semibold uppercase tracking-wider">
        {children}
      </span>
      <div className="border-muted flex-1 border-t" />
    </div>
  );
}

export function ProviderStep({ data, updateData }: ProviderStepProps) {
  const t = useTranslations('Settings.providers');
  const tCommon = useTranslations('Common');

  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [groqModels, setGroqModels] = useState<string[]>([]);
  const [openaiModels, setOpenaiModels] = useState<string[]>([]);
  const [openrouterModels, setOpenrouterModels] = useState<string[]>([]);
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testError, setTestError] = useState<string | null>(null);
  const [testSuccess, setTestSuccess] = useState<string | null>(null);

  useEffect(() => {
    setTestStatus('idle');
    setTestError(null);
    setTestSuccess(null);
  }, [data.llm_provider]);

  // ── Claude CLI ──────────────────────────────────────────────────────────────

  const testClaudeCli = useCallback(async () => {
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-claude-cli', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setTestSuccess(t('claudeCliInstalled'));
      } else {
        setTestStatus('error');
        setTestError(result.error || t('claudeCliNotFound'));
      }
    } catch {
      setTestStatus('error');
      setTestError(t('claudeCliNotFound'));
    }
  }, [t]);

  // ── Gemini CLI ──────────────────────────────────────────────────────────────

  const testGeminiCli = useCallback(async () => {
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-gemini-cli', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setTestSuccess(t('geminiCliInstalled'));
      } else {
        setTestStatus('error');
        setTestError(result.error || t('geminiCliNotFound'));
      }
    } catch {
      setTestStatus('error');
      setTestError(t('geminiCliNotFound'));
    }
  }, [t]);

  // ── Anthropic API ───────────────────────────────────────────────────────────

  const testAnthropic = useCallback(async () => {
    if (!data.anthropic_api_key) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-anthropic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: data.anthropic_api_key }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setTestSuccess(tCommon('connected'));
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Invalid API key');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to validate');
    }
  }, [data.anthropic_api_key, tCommon]);

  // ── Google AI API ───────────────────────────────────────────────────────────

  const testGoogle = useCallback(async () => {
    if (!data.google_api_key) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: data.google_api_key }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setTestSuccess(tCommon('connected'));
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Invalid API key');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to validate');
    }
  }, [data.google_api_key, tCommon]);

  // ── Ollama ──────────────────────────────────────────────────────────────────

  const testOllama = useCallback(async () => {
    if (!data.ollama_host) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-ollama', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: data.ollama_host }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setOllamaModels(result.models || []);
        setTestSuccess(`${tCommon('connected')} — ${t('modelsAvailable', { count: result.models?.length ?? 0 })}`);
        if (!data.ollama_model && result.models?.length > 0) {
          updateData({ ollama_model: result.models[0] });
        }
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Connection failed');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to connect');
    }
  }, [data.ollama_host, data.ollama_model, t, tCommon, updateData]);

  // ── Groq ────────────────────────────────────────────────────────────────────

  const testGroq = useCallback(async () => {
    if (!data.groq_api_key) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-groq', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: data.groq_api_key }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setGroqModels(result.models || []);
        setTestSuccess(`${tCommon('connected')} — ${t('modelsAvailable', { count: result.models?.length ?? 0 })}`);
        if (!data.groq_model && result.models?.length > 0) {
          updateData({ groq_model: result.models[0] });
        }
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Invalid API key');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to validate');
    }
  }, [data.groq_api_key, data.groq_model, t, tCommon, updateData]);

  // ── OpenAI-compatible ───────────────────────────────────────────────────────

  const testOpenAICompatible = useCallback(async () => {
    if (!data.openai_base_url) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-openai-compatible', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: data.openai_base_url, api_key: data.openai_api_key }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setOpenaiModels(result.models || []);
        setTestSuccess(`${tCommon('connected')} — ${t('modelsAvailable', { count: result.models?.length ?? 0 })}`);
        if (!data.openai_model && result.models?.length > 0) {
          updateData({ openai_model: result.models[0] });
        }
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Connection failed');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to connect');
    }
  }, [data.openai_base_url, data.openai_api_key, data.openai_model, t, tCommon, updateData]);

  // ── OpenRouter ──────────────────────────────────────────────────────────────

  const testOpenRouter = useCallback(async () => {
    if (!data.openrouter_api_key) return;
    setTestStatus('testing');
    setTestError(null);
    setTestSuccess(null);
    try {
      const res = await fetch('/api/setup/test-openrouter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: data.openrouter_api_key }),
      });
      const result = await res.json();
      if (result.success) {
        setTestStatus('success');
        setOpenrouterModels(result.models || []);
        setTestSuccess(`${tCommon('connected')} — ${t('modelsAvailable', { count: result.models?.length ?? 0 })}`);
        if (!data.openrouter_model && result.models?.length > 0) {
          updateData({ openrouter_model: result.models[0] });
        }
      } else {
        setTestStatus('error');
        setTestError(result.error || 'Invalid API key');
      }
    } catch {
      setTestStatus('error');
      setTestError('Failed to validate');
    }
  }, [data.openrouter_api_key, data.openrouter_model, t, tCommon, updateData]);

  // ── Shared input + test row component ──────────────────────────────────────

  const InputWithTest = ({
    value,
    onChange,
    placeholder,
    onTest,
    disabled,
    type = 'text',
  }: {
    value: string;
    onChange: (v: string) => void;
    placeholder: string;
    onTest: () => void;
    disabled?: boolean;
    type?: string;
  }) => (
    <div className="flex gap-2">
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="border-input bg-background flex-1 rounded-lg border px-3 py-2 text-sm"
      />
      <button
        onClick={onTest}
        disabled={disabled || testStatus === 'testing'}
        className="bg-muted hover:bg-muted/80 flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm disabled:opacity-40"
      >
        <StatusIcon status={testStatus} />
        {tCommon('test')}
      </button>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Provider grid — grouped */}
      <div>
        <label className="mb-2 block text-sm font-medium">{t('aiProvider')}</label>
        <div className="grid grid-cols-2 gap-2">
          {/* Subscription group */}
          <GroupLabel>Use your subscription</GroupLabel>
          <ProviderCard
            id="claude_cli"
            selected={data.llm_provider === 'claude_cli'}
            onClick={() => updateData({ llm_provider: 'claude_cli' })}
            name="Claude CLI"
            desc={t('claudeCliDesc')}
            badge="free"
          />
          <ProviderCard
            id="gemini_cli"
            selected={data.llm_provider === 'gemini_cli'}
            onClick={() => updateData({ llm_provider: 'gemini_cli' })}
            name="Gemini CLI"
            desc={t('geminiCliDesc')}
            badge="free"
          />

          {/* Cloud API group */}
          <GroupLabel>Cloud API</GroupLabel>
          <ProviderCard
            id="anthropic"
            selected={data.llm_provider === 'anthropic'}
            onClick={() => updateData({ llm_provider: 'anthropic' })}
            name="Anthropic"
            desc={t('anthropicDesc')}
            badge="api"
          />
          <ProviderCard
            id="google"
            selected={data.llm_provider === 'google'}
            onClick={() => updateData({ llm_provider: 'google' })}
            name="Google AI"
            desc={t('googleDesc')}
            badge="api"
          />
          <ProviderCard
            id="groq"
            selected={data.llm_provider === 'groq'}
            onClick={() => updateData({ llm_provider: 'groq' })}
            name="Groq"
            desc={t('groqDesc')}
            badge="api"
          />
          <ProviderCard
            id="openrouter"
            selected={data.llm_provider === 'openrouter'}
            onClick={() => updateData({ llm_provider: 'openrouter' })}
            name="OpenRouter"
            desc={t('openrouterDesc')}
            badge="api"
          />

          {/* Local group */}
          <GroupLabel>Local / Self-hosted</GroupLabel>
          <ProviderCard
            id="ollama"
            selected={data.llm_provider === 'ollama'}
            onClick={() => updateData({ llm_provider: 'ollama' })}
            name="Ollama"
            desc={t('ollamaDesc')}
            badge="local"
          />
          <ProviderCard
            id="openai_compatible"
            selected={data.llm_provider === 'openai_compatible'}
            onClick={() => updateData({ llm_provider: 'openai_compatible' })}
            name="OpenAI Compatible"
            desc={t('openaiCompatibleDesc')}
            badge="local"
          />
        </div>
      </div>

      {/* Status feedback */}
      {testError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{testError}</p>}
      {testSuccess && <p className="rounded-lg bg-green-500/10 px-3 py-2 text-xs text-green-400">{testSuccess}</p>}

      {/* ── Claude CLI settings ── */}
      {data.llm_provider === 'claude_cli' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('claudeCliModel')}</label>
            <select
              value={data.claude_cli_model}
              onChange={(e) => updateData({ claude_cli_model: e.target.value })}
              className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
            >
              {CLAUDE_CLI_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={testClaudeCli}
            disabled={testStatus === 'testing'}
            className="bg-muted hover:bg-muted/80 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm disabled:opacity-40"
          >
            <StatusIcon status={testStatus} />
            Check claude CLI is installed
          </button>
          <p className="text-muted-foreground text-xs">
            Requires the Claude Code CLI. Install from{' '}
            <a href="https://claude.ai/code" target="_blank" rel="noopener noreferrer" className="text-primary underline">
              claude.ai/code
            </a>
          </p>
        </div>
      )}

      {/* ── Gemini CLI settings ── */}
      {data.llm_provider === 'gemini_cli' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('geminiCliModel')}</label>
            <select
              value={data.gemini_cli_model}
              onChange={(e) => updateData({ gemini_cli_model: e.target.value })}
              className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
            >
              {GEMINI_CLI_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={testGeminiCli}
            disabled={testStatus === 'testing'}
            className="bg-muted hover:bg-muted/80 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm disabled:opacity-40"
          >
            <StatusIcon status={testStatus} />
            Check gemini CLI is installed
          </button>
          <p className="text-muted-foreground text-xs">
            Requires the Gemini CLI. Install from{' '}
            <a href="https://ai.google.dev/gemini-api/docs/gemini-cli" target="_blank" rel="noopener noreferrer" className="text-primary underline">
              ai.google.dev
            </a>
          </p>
        </div>
      )}

      {/* ── Anthropic API settings ── */}
      {data.llm_provider === 'anthropic' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('anthropicApiKey')}</label>
            <InputWithTest
              type="password"
              value={data.anthropic_api_key}
              onChange={(v) => updateData({ anthropic_api_key: v })}
              placeholder="sk-ant-..."
              onTest={testAnthropic}
              disabled={!data.anthropic_api_key}
            />
            <p className="text-muted-foreground text-xs">
              {t('getApiKeyAt')}{' '}
              <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer" className="text-primary underline">
                console.anthropic.com
              </a>
            </p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('anthropicModel')}</label>
            <select
              value={data.anthropic_model}
              onChange={(e) => updateData({ anthropic_model: e.target.value })}
              className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
            >
              {CLAUDE_CLI_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* ── Google AI API settings ── */}
      {data.llm_provider === 'google' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('googleApiKey')}</label>
            <InputWithTest
              type="password"
              value={data.google_api_key}
              onChange={(v) => updateData({ google_api_key: v })}
              placeholder="AIza..."
              onTest={testGoogle}
              disabled={!data.google_api_key}
            />
            <p className="text-muted-foreground text-xs">
              {t('getApiKeyAt')}{' '}
              <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="text-primary underline">
                aistudio.google.com
              </a>
            </p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('googleModel')}</label>
            <select
              value={data.google_model}
              onChange={(e) => updateData({ google_model: e.target.value })}
              className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
            >
              {GEMINI_CLI_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* ── Ollama settings ── */}
      {data.llm_provider === 'ollama' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('ollamaHost')}</label>
            <InputWithTest
              value={data.ollama_host}
              onChange={(v) => updateData({ ollama_host: v })}
              placeholder="http://host.docker.internal:11434"
              onTest={testOllama}
              disabled={!data.ollama_host}
            />
          </div>
          {ollamaModels.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t('model')}</label>
              <select
                value={data.ollama_model}
                onChange={(e) => updateData({ ollama_model: e.target.value })}
                className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
              >
                <option value="">{t('selectModel')}</option>
                {ollamaModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}
          <p className="text-muted-foreground text-xs">{t('ollamaSttNote')}</p>
        </div>
      )}

      {/* ── Groq settings ── */}
      {data.llm_provider === 'groq' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('groqApiKey')}</label>
            <InputWithTest
              type="password"
              value={data.groq_api_key}
              onChange={(v) => updateData({ groq_api_key: v })}
              placeholder="gsk_..."
              onTest={testGroq}
              disabled={!data.groq_api_key}
            />
            <p className="text-muted-foreground text-xs">
              {t('getApiKeyAt')}{' '}
              <a href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer" className="text-primary underline">
                console.groq.com
              </a>
            </p>
          </div>
          {groqModels.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t('model')}</label>
              <select
                value={data.groq_model}
                onChange={(e) => updateData({ groq_model: e.target.value })}
                className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
              >
                <option value="">{t('selectModel')}</option>
                {groqModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}
          <p className="text-muted-foreground text-xs">{t('groqSttNote')}</p>
        </div>
      )}

      {/* ── OpenAI-compatible settings ── */}
      {data.llm_provider === 'openai_compatible' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('baseUrl')}</label>
            <InputWithTest
              value={data.openai_base_url}
              onChange={(v) => updateData({ openai_base_url: v })}
              placeholder="http://localhost:8000/v1"
              onTest={testOpenAICompatible}
              disabled={!data.openai_base_url}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">
              {t('apiKey')} <span className="text-muted-foreground font-normal">({t('optional')})</span>
            </label>
            <input
              type="password"
              value={data.openai_api_key}
              onChange={(e) => updateData({ openai_api_key: e.target.value })}
              placeholder="sk-..."
              className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
            />
            <p className="text-muted-foreground text-xs">{t('openaiApiKeyNote')}</p>
          </div>
          {openaiModels.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t('model')}</label>
              <select
                value={data.openai_model}
                onChange={(e) => updateData({ openai_model: e.target.value })}
                className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
              >
                <option value="">{t('selectModel')}</option>
                {openaiModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}
          <p className="text-muted-foreground text-xs">{t('openaiCompatibleSttNote')}</p>
        </div>
      )}

      {/* ── OpenRouter settings ── */}
      {data.llm_provider === 'openrouter' && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('apiKey')}</label>
            <InputWithTest
              type="password"
              value={data.openrouter_api_key}
              onChange={(v) => updateData({ openrouter_api_key: v })}
              placeholder="sk-or-..."
              onTest={testOpenRouter}
              disabled={!data.openrouter_api_key}
            />
            <p className="text-muted-foreground text-xs">
              {t('getApiKeyAt')}{' '}
              <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-primary underline">
                openrouter.ai
              </a>
            </p>
          </div>
          {openrouterModels.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t('model')}</label>
              <select
                value={data.openrouter_model}
                onChange={(e) => updateData({ openrouter_model: e.target.value })}
                className="border-input bg-background w-full rounded-lg border px-3 py-2 text-sm"
              >
                <option value="">{t('selectModel')}</option>
                {openrouterModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {/* STT note when using Groq STT with a different LLM */}
      {data.stt_provider === 'groq' && data.llm_provider !== 'groq' && (
        <div className="space-y-1.5 border-t pt-3">
          <label className="text-sm font-medium">{t('groqApiKey')} (STT)</label>
          <InputWithTest
            type="password"
            value={data.groq_api_key}
            onChange={(v) => updateData({ groq_api_key: v })}
            placeholder="gsk_..."
            onTest={testGroq}
            disabled={!data.groq_api_key}
          />
          <p className="text-muted-foreground text-xs">{t('groqSttNote')}</p>
        </div>
      )}
    </div>
  );
}
