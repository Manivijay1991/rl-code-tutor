// Pure formatting helpers shared by both pages: dates and readable trap names. No DOM, no storage.

/** Today's date in local time, "YYYY-MM-DD" (the key used for daily counts). */
export function today(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const TRAP_WORDS = { ckd: "CKD", htn: "HTN", esrd: "ESRD", meat: "MEAT", z794: "Z79.4", dm: "DM", mdd: "MDD" };

/** Readable trap name from its id: "table:missed_htn_ckd_link" -> "Missed HTN CKD link". */
export function trapName(confusion) {
  const words = confusion.split(":").pop().split("_").map((w) => TRAP_WORDS[w] ?? w);
  const text = words.join(" ");
  return text[0].toUpperCase() + text.slice(1);
}
