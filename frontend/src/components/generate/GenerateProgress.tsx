import type { GenerationStep } from "../../types/document";
import "./GenerateProgress.css";

function icon(status: GenerationStep["status"]): string {
  if (status === "done") return "✓";
  if (status === "active") return "●";
  return "○";
}

export function GenerateProgress({ steps }: { steps: GenerationStep[] }) {
  return (
    <section className="generate-progress surface" aria-live="polite">
      <p className="generate-progress__heading">Generating...</p>
      <ul className="generate-progress__list">
        {steps.map((step) => (
          <li key={step.key} className={`generate-progress__item generate-progress__item--${step.status}`}>
            <span className="generate-progress__icon">{icon(step.status)}</span>
            <span>{step.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
