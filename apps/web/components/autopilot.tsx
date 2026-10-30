import { setAutopilot } from "@/app/inbox/actions";
import { Submit } from "@/components/client";
import { Alert, Card, Locked, When } from "@/components/ui";

export interface ReportOption { id: string; code: string; report_mode: string; information_cutoff: string }
export interface AutopilotRow { report_id: string; enabled: boolean; reason: string; changed_at: string }

/** CR7-05 — the automatic analysis switch for ONE report (= one analysis context). Starting it is a human, audited act. */
export function AutopilotCard({ reports, state, allowed, fixedReport }: {
  reports: ReportOption[]; state: AutopilotRow[]; allowed: boolean; fixedReport?: string;
}) {
  const on = state.find((s) => s.enabled);
  const onReport = on ? reports.find((r) => r.id === on.report_id) : undefined;
  return (
    <Card title="Autopilot (automatic analysis)" tone={on ? "accent" : undefined}>
      {on ? (
        <Alert kind="success" title="ON.">
          New claims of <b>{onReport?.code ?? "the selected report"}</b> ({onReport?.report_mode}, cutoff{" "}
          <When at={onReport?.information_cutoff} />) are turned into events, scored, assessed and challenged automatically.
          Nothing is approved without you: you confirm events and approve assessments in your inbox.
        </Alert>
      ) : (
        <p className="muted" style={{ marginTop: 0 }}>Off. Switch it on for one report and the system builds events, scores relevance, drafts
          assessments and challenges them by itself. Up to 20 automatic assessments per report keep the cost bounded.</p>
      )}
      {!allowed ? <Locked>Switching the autopilot needs EVENT_ACTION (analyst).</Locked> : (
        <form action={setAutopilot} className="form">
          <div className="form-row">
            {fixedReport ? <input type="hidden" name="report_id" value={fixedReport} /> : (
              <div className="field"><label htmlFor="ap-report">Report (analysis context)</label>
                <select id="ap-report" name="report_id" required defaultValue={on?.report_id ?? reports[0]?.id}>
                  {reports.map((r) => <option key={r.id} value={r.id}>{r.code} · {r.report_mode} · cutoff {r.information_cutoff.replace("T", " ").slice(0, 16)}</option>)}
                </select></div>
            )}
            <div className="field"><label htmlFor="ap-reason">Reason (audited)</label>
              <input id="ap-reason" name="reason" required minLength={5} defaultValue={on ? "pause the automatic analysis" : "run the analysis automatically for this report"} /></div>
          </div>
          <div className="row">
            {on && (!fixedReport || on.report_id === fixedReport) && <Submit name="enabled" value="off" kind="danger">Switch autopilot off</Submit>}
            {(!on || (fixedReport && on.report_id !== fixedReport)) && !on && <Submit name="enabled" value="on" kind="primary">Switch autopilot on</Submit>}
          </div>
          {on && fixedReport && on.report_id !== fixedReport && <p className="muted" style={{ margin: 0 }}>It is on for another report; switch that one off first.</p>}
        </form>
      )}
    </Card>
  );
}
