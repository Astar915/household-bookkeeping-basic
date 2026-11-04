import { WorkflowEntrypoint } from "cloudflare:workers";

const MAX_ADVANCES = 34;

export class AppJobWorkflow extends WorkflowEntrypoint {
  async run(event, step) {
    const payload = event?.payload || event;
    const userId = String(payload?.userId || "");
    const operationId = String(payload?.operationId || "");
    const action = String(payload?.action || "");
    const secret = String(this.env.APP_JOB_SHARED_SECRET || "");
    if (!userId || userId.length > 80 || !/^[A-Za-z0-9_-]{12,80}$/.test(operationId) || !secret) {
      throw new Error("Invalid or incomplete app job configuration.");
    }

    for (let index = 0; index < MAX_ADVANCES; index += 1) {
      let outcome;
      try {
        outcome = await step.do(`advance_${index}`, {
          retries: { limit: 2, delay: "2 seconds", backoff: "exponential" },
        }, async () => {
          const request = new Request("https://job-runner.internal/__internal/job/advance", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-App-Job-Secret": secret,
              "X-App-Job-Action": action,
            },
            body: JSON.stringify({ userId, operationId }),
          });
          const response = await this.env.PYTHON_API.fetch(request);
          if (!response.ok) {
            let diagnostic=null;
            try {
              const body=await response.clone().json();
              const type=String(body?.diagnostic?.type||"");
              const locations=String(body?.diagnostic?.locations||"");
              if(/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(type)
                &&locations.length<=400&&/^[A-Za-z0-9_.:/ >-]*$/.test(locations)){
                diagnostic=` [diag:${type}@${locations}]`;
              }
            } catch {}
            throw new Error(`Python job service returned ${response.status}.${diagnostic||""}`);
          }
          const result = await response.json();
          if (!["continue", "done", "failed", "cancelled"].includes(result?.state)) {
            throw new Error("Python job service returned an invalid state.");
          }
          // Persist only a status marker. User text, ledger values, receipt data,
          // OAuth tokens, and model keys remain in the Python worker and D1.
          return { state: result.state };
        });
      } catch (error) {
        // Stop polling on an unavailable Python engine without claiming that a
        // resource quota was exceeded. Only an allow-listed HTTP status and a
        // sanitized exception type/source location may reach the job message.
        const failureText=String(error?.message||"");
        const status=failureText.match(/Python job service returned (\d{3})/i)?.[1]||"";
        const match=failureText.match(/\[diag:([A-Za-z][A-Za-z0-9_]{0,63})@([A-Za-z0-9_.:/ >-]{0,400})\]/);
        const diagnostic=match?`（${match[1]}：${match[2]}）`:"";
        const detail=status?`（HTTP ${status}）`:"";
        const actionMessage=action==="agent_prepare"
          ?"本次图片记账未提交，账本没有因此修改。"
          :"请刷新核对操作状态后再决定是否重试。";
        const message=`云端后台服务暂时不可用${detail}${diagnostic}。${actionMessage}`;
        const result = JSON.stringify({ error: message });
        await this.env.DB.batch([
          this.env.DB.prepare(
          "UPDATE app_jobs SET state='failed',message=?,result_json=?,updated_at=? " +
          "WHERE user_id=? AND operation_id=? AND state IN ('queued','running')"
          ).bind(message, result, new Date().toISOString(), userId, operationId),
          this.env.DB.prepare(
            "DELETE FROM app_job_model_call_chunks WHERE user_id=? AND operation_id=?"
          ).bind(userId, operationId),
          this.env.DB.prepare(
            "DELETE FROM app_job_model_calls WHERE user_id=? AND operation_id=?"
          ).bind(userId, operationId),
          this.env.DB.prepare(
            "DELETE FROM app_job_payload_chunks WHERE user_id=? AND operation_id=?"
          ).bind(userId, operationId),
          this.env.DB.prepare(
            "DELETE FROM app_job_payloads WHERE user_id=? AND operation_id=?"
          ).bind(userId, operationId),
        ]);
        return { state: "failed" };
      }

      if (outcome.state !== "continue") return { state: outcome.state };
    }

    throw new Error("App job exceeded its provider-call limit.");
  }
}

export default {
  async fetch() {
    return new Response("Not found", { status: 404 });
  },
};
