/** The request for Dev on a development's Pre or Post, ready in the
 * agent panel (not sent): the task, its repository and the phase's suggested steps. */
export function devRequest(task: { name: string; title: string; pre?: { steps?: string[] }; post?: { steps?: string[] } }, phase: "pre" | "post",
  repository = ""): string {
  const kind = phase === "post" ? "il post" : "il pre";
  const where = repository ? ` sul repository ${repository}` : "";
  const steps = ((phase === "post" ? task.post : task.pre)?.steps ?? []).filter((step) => step.trim());
  const list = steps.length ? `\nPassi:\n${steps.map((step) => `- ${step}`).join("\n")}` : "";
  return `Fai ${kind} dello sviluppo «${task.title}» (${task.name})${where}.${list}\nAlla fine dimmi in una riga cosa hai fatto.`;
}
