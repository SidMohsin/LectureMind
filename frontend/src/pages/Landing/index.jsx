import { Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Footer from "../../components/layout/Footer";
import Logo from "../../components/brand/Logo";
import {
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  FileTextIcon,
  LayersIcon,
  LightbulbIcon,
  LockIcon,
  MessageIcon,
  PlayIcon,
  SearchIcon,
  ShieldIcon,
  UploadIcon,
} from "../../components/ui/icons";
import { useAuth } from "../../auth/AuthContext";
import "./Landing.css";

const STEPS = [
  { icon: UploadIcon, title: "Add a lecture", text: "Upload a video or audio recording, or paste a YouTube link." },
  { icon: FileTextIcon, title: "Transcribed with timestamps", text: "Every sentence keeps the exact moment it was spoken." },
  { icon: LayersIcon, title: "Structured for you", text: "Chapters, a summary, key concepts and definitions are generated." },
  { icon: MessageIcon, title: "Ask and jump", text: "Ask questions and click a source to hear that part of the lecture." },
];

const FEATURES = [
  { icon: FileTextIcon, title: "Timestamped transcript", text: "Follows playback as the lecture plays. Click any line to jump to that moment." },
  { icon: LayersIcon, title: "Chapters", text: "The lecture is split into named sections you can skim and jump between." },
  { icon: LightbulbIcon, title: "Key concepts", text: "Concepts, definitions and keywords taken from what was actually taught." },
  { icon: SearchIcon, title: "Search your library", text: "Find the passage where a topic is explained, across all your lectures." },
  { icon: MessageIcon, title: "Answers with sources", text: "Every answer shows the passages it used, each linked to its timestamp." },
  { icon: ShieldIcon, title: "Says when it doesn't know", text: "If the lecture doesn't cover a question, LectureMind tells you instead of guessing." },
];

const USE_CASES = [
  "Revise for an exam without rewatching whole lectures",
  "Find the one explanation you half-remember",
  "See the structure of a long, dense lecture at a glance",
  "Go straight back to a specific moment",
];

/**
 * In-page links (#how-it-works, #features) glide to their section. Done here rather
 * than with CSS `scroll-behavior`, which would also animate the scroll-to-top on
 * every page change. Respects the "reduce motion" setting.
 */
function scrollToSection(event) {
  const link = event.target.closest?.('a[href^="#"]');
  if (!link) return;
  const target = document.getElementById(decodeURIComponent(link.getAttribute("href").slice(1)));
  if (!target) return;
  event.preventDefault();
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  window.history.replaceState(window.history.state, "", link.getAttribute("href"));
}

export default function Landing() {
  const { status } = useAuth();

  // Signed-in users can still read this page; every call to action takes them to their app.
  const signedIn = status === "authenticated";
  const primary = signedIn ? { to: "/dashboard", label: "Go to Dashboard" } : { to: "/signup", label: "Get Started" };

  return (
    // Catches clicks bubbling up from the page's own #section links (keyboard Enter on a link clicks too).
    <div className="landing" onClick={scrollToSection}>
      <header className="landing-header">
        <div className="landing-header__inner">
          <Link to="/" className="landing-header__brand" aria-label="LectureMind home">
            <Logo />
          </Link>
          <nav className="landing-header__nav" aria-label="Page sections">
            <a href="#how-it-works">How it works</a>
            <a href="#features">Features</a>
          </nav>
          <div className="landing-header__actions">
            {!signedIn && (
              <Button as={Link} to="/login" variant="tertiary">
                Log In
              </Button>
            )}
            <Button as={Link} to={primary.to} variant="primary">
              {primary.label}
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero__copy">
            <p className="landing-eyebrow">Lecture intelligence platform</p>
            <h1 className="landing-hero__title">Turn lectures into knowledge you can actually use.</h1>
            <p className="landing-hero__subtitle">
              LectureMind turns recorded lectures into a timestamped transcript, chapters and key concepts — and
              answers your questions using only what the lecture says, with a link to the exact moment.
            </p>
            <div className="landing-hero__actions">
              <Button as={Link} to={primary.to} variant="primary" className="landing-hero__cta">
                {primary.label} <ArrowRightIcon size={16} />
              </Button>
              <Button as="a" href="#how-it-works" variant="secondary">
                See how it works
              </Button>
            </div>
            <ul className="landing-hero__points">
              <li>
                <CheckIcon size={16} /> Video, audio or YouTube link
              </li>
              <li>
                <CheckIcon size={16} /> Answers cite timestamps
              </li>
              <li>
                <LockIcon size={16} /> Private to your account
              </li>
            </ul>
          </div>
          <ProductPreview />
        </section>

        <section className="landing-section" id="how-it-works" aria-labelledby="how-heading">
          <p className="landing-eyebrow">How it works</p>
          <h2 id="how-heading" className="landing-section__heading">
            From recording to answers in four steps
          </h2>
          <ol className="landing-steps">
            {STEPS.map(({ icon: Icon, title, text }, index) => (
              <li key={title} className="landing-step">
                <span className="landing-step__number mono">{String(index + 1).padStart(2, "0")}</span>
                <span className="landing-step__icon">
                  <Icon size={20} />
                </span>
                <h3>{title}</h3>
                <p>{text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section" id="features" aria-labelledby="features-heading">
          <p className="landing-eyebrow">Features</p>
          <h2 id="features-heading" className="landing-section__heading">
            Everything links back to a moment in the lecture
          </h2>
          <div className="landing-features">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <article key={title} className="landing-feature">
                <span className="landing-feature__icon">
                  <Icon size={20} />
                </span>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section landing-uses" aria-labelledby="uses-heading">
          <div>
            <p className="landing-eyebrow">Made for studying</p>
            <h2 id="uses-heading" className="landing-section__heading landing-uses__heading">
              Spend your time understanding, not scrubbing through video
            </h2>
          </div>
          <ul className="landing-uses__list">
            {USE_CASES.map((useCase) => (
              <li key={useCase}>
                <span className="landing-uses__check">
                  <CheckIcon size={14} />
                </span>
                {useCase}
              </li>
            ))}
          </ul>
        </section>

        <section className="landing-cta">
          <h2 className="landing-cta__title">
            {signedIn ? "Pick up where you left off." : "Start turning your lectures into a knowledge base."}
          </h2>
          <p className="landing-cta__description">
            {signedIn ? "Your lectures, notes and questions are waiting in your dashboard." : "Create a free account and add your first lecture."}
          </p>
          <Button as={Link} to={primary.to} variant="secondary" className="landing-cta__button">
            {primary.label} <ArrowRightIcon size={16} />
          </Button>
        </section>
      </main>

      <Footer
        links={
          signedIn
            ? [
                { href: "#how-it-works", label: "How it works" },
                { to: "/dashboard", label: "Dashboard" },
                { to: "/library", label: "Library" },
              ]
            : [
                { href: "#how-it-works", label: "How it works" },
                { to: "/login", label: "Log in" },
                { to: "/signup", label: "Create account" },
              ]
        }
      />
    </div>
  );
}

/** Illustration of the workspace (static markup, not real data). */
function ProductPreview() {
  return (
    <div className="preview" aria-hidden="true">
      <div className="preview__bar">
        <span />
        <span />
        <span />
        <p className="mono">Lecture 4 · Gradient Descent</p>
      </div>
      <div className="preview__body">
        <div className="preview__player">
          <div className="preview__chapter">
            <span className="preview__dot" /> Chapter 3 · Choosing the learning rate
          </div>
          <div className="preview__controls">
            <span className="preview__play">
              <PlayIcon size={14} />
            </span>
            <div className="preview__track">
              <span className="preview__progress" />
              <span className="preview__marks" />
            </div>
            <span className="mono preview__time">18:42</span>
          </div>
        </div>
        <ul className="preview__transcript">
          <li>
            <span className="mono">18:31</span> So how big should each step be?
          </li>
          <li className="is-active">
            <span className="mono">18:42</span> If the learning rate is too large, the loss starts to oscillate…
          </li>
          <li>
            <span className="mono">18:55</span> …and if it’s too small, training takes forever.
          </li>
        </ul>
        <div className="preview__qa">
          <p className="preview__question">
            <MessageIcon size={14} /> Why can a large learning rate fail?
          </p>
          <p className="preview__answer">
            The lecture explains that a large step can overshoot the minimum, so the loss oscillates instead of
            decreasing.
          </p>
          <div className="preview__sources">
            <span>
              <ClockIcon size={12} /> 18:42
            </span>
            <span>
              <ClockIcon size={12} /> 21:07
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
