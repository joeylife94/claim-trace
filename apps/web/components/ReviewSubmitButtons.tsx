"use client";

import { useFormStatus } from "react-dom";

export function ReviewSubmitButtons() {
  const { pending } = useFormStatus();

  return (
    <>
      <button type="submit" name="status" value="accepted" disabled={pending}>
        {pending ? "Saving review…" : "Accept decomposition"}
      </button>
      <button type="submit" name="status" value="needs_correction" disabled={pending}>
        {pending ? "Saving review…" : "Mark needs correction"}
      </button>
    </>
  );
}
