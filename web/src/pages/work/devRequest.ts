/** The request for Dev on a pre/post development task (plan 22), ready in the
 * agent panel (not sent): the task, its repository and its suggested steps. */
export function devRequest(task: { name: string; title: string; type?: string; steps?: string[] }, repository = ""): string {
  const kind = task.type === "post_dev" ? "post sviluppo" : "pre sviluppo";
  const where = repository ? ` sul repository ${repository}` : "";
  const steps = (task.steps ?? []).filter((step) => step.trim());
  const list = steps.length ? `\nPassi:\n${steps.map((step) => `- ${step}`).join("\n")}` : "";
  return `Fai il task ${kind} «${task.title}» (${task.name})${where}.${list}\nAlla fine dimmi in una riga cosa hai fatto.`;
}
