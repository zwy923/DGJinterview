export async function askGPT(prompt: string): Promise<string> {
  const res = await fetch("http://localhost:8000/api/gpt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  const data = await res.json();
  return data.reply || "（无回应）";
}
