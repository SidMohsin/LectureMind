import { useCallback, useEffect, useState } from "react";
import PageContainer from "../../components/layout/PageContainer";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import { getMe } from "../../services/account";
import "./Profile.css";

const dateFormat = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "long", day: "numeric" });

export default function Profile() {
  const [state, setState] = useState({ status: "loading", me: null, error: null });

  const load = useCallback((signal) => {
    setState({ status: "loading", me: null, error: null });
    getMe({ signal })
      .then((me) => setState({ status: "ready", me, error: null }))
      .catch((error) => {
        if (error.name !== "AbortError") setState({ status: "error", me: null, error });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <PageContainer>
      <div className="profile">
        <h1 className="profile__title">Profile</h1>
        <p className="profile__subtitle">Your LectureMind account.</p>

        {state.status === "error" && (
          <Alert tone="error" title="We couldn't load your profile.">
            {state.error.message}{" "}
            <Button variant="tertiary" onClick={() => load()}>
              Try again
            </Button>
          </Alert>
        )}

        {state.status !== "error" && (
          <Card aria-busy={state.status === "loading"}>
            <dl className="profile__fields">
              <Field label="Name" value={state.me?.display_name || "Not set"} loading={state.status === "loading"} />
              <Field label="Email" value={state.me?.email} loading={state.status === "loading"} />
              <Field
                label="Member since"
                value={state.me && dateFormat.format(new Date(state.me.created_at))}
                loading={state.status === "loading"}
              />
            </dl>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}

function Field({ label, value, loading }) {
  return (
    <div className="profile__field">
      <dt className="profile__label">{label}</dt>
      <dd className="profile__value">{loading ? <span className="profile__skeleton" /> : value}</dd>
    </div>
  );
}
