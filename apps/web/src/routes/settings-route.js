import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { useSettings, useUpdateSettings } from "@/features/settings/use-settings";
export function SettingsRoute() {
    const settings = useSettings();
    const updateSettings = useUpdateSettings();
    const [form, setForm] = useState({});
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
    ];
    const weightKeys = [
        "technical_quality",
        "composition",
        "subject_state",
        "rarity",
    ];
    const thresholdKeys = [
        "star_5",
        "star_4",
        "star_3",
        "star_2",
        "reject",
    ];
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
    const provider = form.ai_provider ?? settings.data?.ai_provider ?? "lm_studio";
    const runtimeKeys = provider === "openrouter" ? ["ai_base_url", "ai_model_name", "allow_remote_ai", ...baseEditableKeys] : ["ai_base_url", "ai_model_name", ...baseEditableKeys];
    const handleProviderChange = (nextProvider) => {
        setForm((current) => ({
            ...current,
            ai_provider: nextProvider,
            ai_base_url: nextProvider === "openrouter" ? "https://openrouter.ai/api/v1" : "http://127.0.0.1:1234/v1",
        }));
    };
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Tunable thresholds without breaking reproducibility.", copy: "MVP \u3067\u306F\u904B\u7528\u4E0A\u91CD\u8981\u306A\u9805\u76EE\u3060\u3051\u3092 UI \u5316\u3057\u3001\u6B8B\u308A\u306F\u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u7BA1\u7406\u306B\u6B8B\u3057\u307E\u3059\u3002\u30B8\u30E7\u30D6\u958B\u59CB\u6642\u306E\u30B9\u30CA\u30C3\u30D7\u30B7\u30E7\u30C3\u30C8\u4FDD\u5B58\u306F API \u5074\u3067\u884C\u3044\u307E\u3059\u3002", badge: "Settings" }), _jsxs(Panel, { title: "Runtime Settings", copy: "LM Studio \u63A5\u7D9A\u3068\u8A55\u4FA1\u95BE\u5024\u306E\u6700\u5C0F\u69CB\u6210", children: [_jsxs("div", { className: "field-grid", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "ai_provider", children: "ai_provider" }), _jsxs("select", { id: "ai_provider", value: provider, onChange: (event) => handleProviderChange(event.target.value), children: [_jsx("option", { value: "lm_studio", children: "lm_studio" }), _jsx("option", { value: "openrouter", children: "openrouter" })] })] }), runtimeKeys.map((key) => (_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: key, children: key }), key === "allow_remote_ai" ? (_jsxs("select", { id: key, value: form[key] ?? "false", onChange: (event) => setForm((current) => ({ ...current, [key]: event.target.value })), children: [_jsx("option", { value: "false", children: "false" }), _jsx("option", { value: "true", children: "true" })] })) : (_jsx("input", { id: key, value: form[key] ?? "", onChange: (event) => setForm((current) => ({ ...current, [key]: event.target.value })) }))] }, key))), weightKeys.map((key) => {
                                const fieldKey = `weights.${key}`;
                                return (_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: fieldKey, children: fieldKey }), _jsx("input", { id: fieldKey, value: form[fieldKey] ?? "", onChange: (event) => setForm((current) => ({ ...current, [fieldKey]: event.target.value })) })] }, fieldKey));
                            }), thresholdKeys.map((key) => {
                                const fieldKey = `rating_thresholds.${key}`;
                                return (_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: fieldKey, children: fieldKey }), _jsx("input", { id: fieldKey, value: form[fieldKey] ?? "", onChange: (event) => setForm((current) => ({ ...current, [fieldKey]: event.target.value })) })] }, fieldKey));
                            })] }), provider === "openrouter" ? (_jsxs("p", { className: "panel-copy", style: { marginTop: 16 }, children: ["API key is read from env via ", _jsx("code", { children: "SKYSORT_AI_API_KEY" }), ". Optional OpenRouter headers use ", _jsx("code", { children: "SKYSORT_AI_REFERER" }), " and ", _jsx("code", { children: "SKYSORT_AI_TITLE" }), "."] })) : null, _jsx("div", { className: "actions", style: { marginTop: 20 }, children: _jsx("button", { className: "button", type: "button", onClick: () => updateSettings.mutate({
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
                            }), children: "Save Settings" }) })] })] }));
}
