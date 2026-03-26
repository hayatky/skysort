import { useEffect, useState } from "react";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { useSettings, useUpdateSettings } from "@/features/settings/use-settings";

export function SettingsRoute() {
  const settings = useSettings();
  const updateSettings = useUpdateSettings();
  const [form, setForm] = useState<Record<string, string>>({});
  const baseEditableKeys = [
    "ai_concurrency",
    "image_processing_concurrency",
    "similarity_threshold",
    "time_proximity_seconds",
    "candidate_limit",
    "thumbnail_size",
    "preview_size",
    "compare_preview_size",
    "preview_jpeg_quality",
    "highlight_threshold",
    "shadow_threshold",
    "exiftool_path",
  ] as const;
  const weightKeys = [
    "technical_quality",
    "composition",
    "subject_state",
    "rarity",
  ] as const;
  const thresholdKeys = [
    "star_5",
    "star_4",
    "star_3",
    "star_2",
    "reject",
  ] as const;

  useEffect(() => {
    if (settings.data) {
      setForm({
        ai_provider: settings.data.ai_provider,
        ai_base_url: settings.data.ai_base_url,
        ai_model_name: settings.data.ai_model_name,
        allow_remote_ai: String(settings.data.allow_remote_ai),
        ...Object.fromEntries(baseEditableKeys.map((key) => [key, String(settings.data[key])])),
        ...Object.fromEntries(weightKeys.map((key) => [`weights.${key}`, String(settings.data.weights[key])])),
        ...Object.fromEntries(thresholdKeys.map((key) => [`rating_thresholds.${key}`, String(settings.data.rating_thresholds[key])])),
      });
    }
  }, [settings.data]);

  const provider = (form.ai_provider ?? settings.data?.ai_provider ?? "lm_studio") as "lm_studio" | "openrouter";
  const runtimeKeys = provider === "openrouter" ? ["ai_base_url", "ai_model_name", "allow_remote_ai", ...baseEditableKeys] : ["ai_base_url", "ai_model_name", ...baseEditableKeys];

  const handleProviderChange = (nextProvider: "lm_studio" | "openrouter") => {
    setForm((current) => ({
      ...current,
      ai_provider: nextProvider,
      ai_base_url: nextProvider === "openrouter" ? "https://openrouter.ai/api/v1" : "http://127.0.0.1:1234/v1",
    }));
  };

  return (
    <>
      <Hero
        title="Tunable thresholds without breaking reproducibility."
        copy="MVP では運用上重要な項目だけを UI 化し、残りは設定ファイル管理に残します。ジョブ開始時のスナップショット保存は API 側で行います。"
        badge="Settings"
      />
      <Panel title="Runtime Settings" copy="LM Studio 接続と評価閾値の最小構成">
        <div className="field-grid">
          <div className="field">
            <label htmlFor="ai_provider">ai_provider</label>
            <select id="ai_provider" value={provider} onChange={(event) => handleProviderChange(event.target.value as "lm_studio" | "openrouter")}>
              <option value="lm_studio">lm_studio</option>
              <option value="openrouter">openrouter</option>
            </select>
          </div>
          {runtimeKeys.map((key) => (
            <div className="field" key={key}>
              <label htmlFor={key}>{key}</label>
              {key === "allow_remote_ai" ? (
                <select id={key} value={form[key] ?? "false"} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}>
                  <option value="false">false</option>
                  <option value="true">true</option>
                </select>
              ) : (
                <input id={key} value={form[key] ?? ""} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} />
              )}
            </div>
          ))}
          {weightKeys.map((key) => {
            const fieldKey = `weights.${key}`;
            return (
              <div className="field" key={fieldKey}>
                <label htmlFor={fieldKey}>{fieldKey}</label>
                <input id={fieldKey} value={form[fieldKey] ?? ""} onChange={(event) => setForm((current) => ({ ...current, [fieldKey]: event.target.value }))} />
              </div>
            );
          })}
          {thresholdKeys.map((key) => {
            const fieldKey = `rating_thresholds.${key}`;
            return (
              <div className="field" key={fieldKey}>
                <label htmlFor={fieldKey}>{fieldKey}</label>
                <input id={fieldKey} value={form[fieldKey] ?? ""} onChange={(event) => setForm((current) => ({ ...current, [fieldKey]: event.target.value }))} />
              </div>
            );
          })}
        </div>
        {provider === "openrouter" ? (
          <p className="panel-copy" style={{ marginTop: 16 }}>
            API key is read from env via <code>SKYSORT_AI_API_KEY</code>. Optional OpenRouter headers use <code>SKYSORT_AI_REFERER</code> and <code>SKYSORT_AI_TITLE</code>.
          </p>
        ) : null}
        <div className="actions" style={{ marginTop: 20 }}>
          <button
            className="button"
            type="button"
            onClick={() =>
              updateSettings.mutate({
                ai_provider: provider,
                ai_base_url: form.ai_base_url,
                ai_model_name: form.ai_model_name,
                allow_remote_ai: form.allow_remote_ai === "true",
                ai_concurrency: Number(form.ai_concurrency),
                image_processing_concurrency: Number(form.image_processing_concurrency),
                similarity_threshold: Number(form.similarity_threshold),
                time_proximity_seconds: Number(form.time_proximity_seconds),
                candidate_limit: Number(form.candidate_limit),
                thumbnail_size: Number(form.thumbnail_size),
                preview_size: Number(form.preview_size),
                compare_preview_size: Number(form.compare_preview_size),
                preview_jpeg_quality: Number(form.preview_jpeg_quality),
                highlight_threshold: Number(form.highlight_threshold),
                shadow_threshold: Number(form.shadow_threshold),
                exiftool_path: form.exiftool_path,
                weights: {
                  technical_quality: Number(form["weights.technical_quality"]),
                  composition: Number(form["weights.composition"]),
                  subject_state: Number(form["weights.subject_state"]),
                  rarity: Number(form["weights.rarity"]),
                },
                rating_thresholds: {
                  star_5: Number(form["rating_thresholds.star_5"]),
                  star_4: Number(form["rating_thresholds.star_4"]),
                  star_3: Number(form["rating_thresholds.star_3"]),
                  star_2: Number(form["rating_thresholds.star_2"]),
                  reject: Number(form["rating_thresholds.reject"]),
                },
              })
            }
          >
            Save Settings
          </button>
        </div>
      </Panel>
    </>
  );
}
