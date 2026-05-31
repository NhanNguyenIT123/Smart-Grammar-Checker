import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  BookOpen,
  ChevronDown,
  Eraser,
  GraduationCap,
  HelpCircle,
  ListChecks,
  PlusCircle,
  SendHorizontal,
  Sparkles,
  Users,
} from "lucide-react";
import checkerbg from "@/assets/mainpage/mainpagebg.svg";
import WorkspaceNavbar from "@/components/WorkspaceNavbar";
import ResultTemplates from "@/components/grammar/ResultTemplates";
import {
  createClass,
  executeDslCommand,
  fetchCurrentUser,
  getClassDetail,
  getQuizAttempts,
  getQuizDetail,
  joinClass,
  listClasses,
  listClassQuizzes,
  loadStoredUser,
  logoutCurrentUser,
  updateActivity,
} from "@/lib/api";

const DEFAULT_COMMAND = "help";

function formatPanelTitle(command) {
  if (!command) {
    return "Command Output";
  }
  return String(command)
    .split(/\s+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function sanitizeAnswerForDsl(text) {
  return String(text || "").replace(/"/g, "'").trim();
}

export default function GrammarWorkspace() {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(loadStoredUser());
  const [input, setInput] = useState(DEFAULT_COMMAND);
  const [submittedInput, setSubmittedInput] = useState("");
  const [result, setResult] = useState(null);
  const [playgroundExercises, setPlaygroundExercises] = useState(null);
  const [loading, setLoading] = useState(false);
  const [banner, setBanner] = useState("");
  const [activeView, setActiveView] = useState("playground");
  const [classes, setClasses] = useState([]);
  const [selectedClassId, setSelectedClassId] = useState(null);
  const [classDetail, setClassDetail] = useState(null);
  const [classQuizzes, setClassQuizzes] = useState([]);
  const [selectedQuizId, setSelectedQuizId] = useState(null);
  const [quizDetail, setQuizDetail] = useState(null);
  const [quizAttempts, setQuizAttempts] = useState([]);
  const [tutorQuizAction, setTutorQuizAction] = useState(null); // "preview" or "scorebook"
  const [expandedStudentUsername, setExpandedStudentUsername] = useState(null);
  const [className, setClassName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [quizBuilder, setQuizBuilder] = useState({
    title: "Starter Grammar Quiz",
    count: 5,
    features: "(present simple AND affirmative) OR (past simple AND interrogative)",
  });
  const [quizAnswers, setQuizAnswers] = useState({});
  const [activeScorebookFilter, setActiveScorebookFilter] = useState("");
  const previousViewRef = useRef("playground");
  const playgroundSnapshotRef = useRef({
    input: DEFAULT_COMMAND,
    submittedInput: "",
    result: null,
    playgroundExercises: null,
  });

  const isTutor = currentUser?.role === "tutor";

  const questionStats = useMemo(() => {
    if (!quizAttempts || !quizAttempts.length) return { items: [], submittedCount: 0 };
    const stats = {};
    let submittedCount = 0;
    quizAttempts.forEach((attempt) => {
      // Handle flexible payload structure (either direct grading or nested in grading property)
      const grading = attempt.submission_payload?.grading || attempt.submission_payload;
      const results = grading?.item_results || [];
      
      if (results.length) submittedCount++;
      results.forEach((res, idx) => {
        if (!stats[idx]) stats[idx] = { total: 0, correct: 0, prompt: res.prompt };
        stats[idx].total++;
        if (res.score > 0 || res.is_correct === true) stats[idx].correct++;
      });
    });
    return { items: Object.values(stats), submittedCount };
  }, [quizAttempts]);

  const renderQuizResults = (detail, attempts) => {
    if (!detail) return null;
    const myAttempt = detail.attempt || attempts.find((a) => a.username === currentUser?.username);
    const grading = myAttempt?.submission_payload?.grading || myAttempt?.submission_payload;

    if (!myAttempt) {
      return (
        <div className="bad-input-box" style={{ marginTop: "1.5rem", padding: "1.5rem", textAlign: "center" }}>
          <AlertCircle size={32} style={{ margin: "0 auto 1rem", color: "#6B7280" }} />
          <p style={{ fontWeight: 500 }}>You haven't submitted this quiz yet.</p>
          <button 
            type="button" 
            className="suggestion-cta" 
            style={{ marginTop: "1rem", marginInline: "auto" }}
            onClick={() => setActiveView("classes")}
          >
            Go to Classes to take the quiz
          </button>
        </div>
      );
    }

    return (
      <div style={{ marginTop: "1.5rem" }}>
        <ResultTemplates.QuizScore data={grading} />
      </div>
    );
  };

  useEffect(() => {
    const restore = async () => {
      // Force clear any hanging overlays or body styles from previous pages
      document.body.style.overflow = "auto";
      document.body.style.pointerEvents = "auto";
      
      const stored = loadStoredUser();
      if (!stored) {
        navigate("/login", { replace: true });
        return;
      }

      const user = await fetchCurrentUser(stored.id);
      if (!user) {
        navigate("/login", { replace: true });
        return;
      }

      updateActivity();
      setCurrentUser(user);
    };

    restore();
  }, [navigate]);

  useEffect(() => {
    if (!currentUser?.id) {
      return;
    }

    const load = async () => {
      try {
        const nextClasses = await listClasses(currentUser.id);
        setClasses(nextClasses);
        if (!nextClasses.length) {
          setSelectedClassId(null);
          setSelectedQuizId(null);
          setClassDetail(null);
          setClassQuizzes([]);
          setQuizDetail(null);
          setQuizAttempts([]);
          return;
        }
        if (!selectedClassId || !nextClasses.some((entry) => entry.id === selectedClassId)) {
          setSelectedClassId(nextClasses[0].id);
        }
      } catch (error) {
        setBanner(error.message);
      }
    };

    load();
  }, [currentUser?.id]);

  useEffect(() => {
    if (!currentUser?.id || !selectedClassId) {
      setClassDetail(null);
      setClassQuizzes([]);
      setSelectedQuizId(null);
      return;
    }

    const loadClassContext = async () => {
      try {
        const [detail, quizzes] = await Promise.all([
          getClassDetail(selectedClassId, currentUser.id),
          listClassQuizzes(selectedClassId, currentUser.id),
        ]);
        setClassDetail(detail);
        setClassQuizzes(quizzes);
        if (!quizzes.length) {
          setSelectedQuizId(null);
          setQuizDetail(null);
          setQuizAttempts([]);
          return;
        }
        if (selectedQuizId && !quizzes.some((entry) => entry.id === selectedQuizId)) {
          setSelectedQuizId(null);
          setTutorQuizAction(null);
        }
      } catch (error) {
        setBanner(error.message);
      }
    };

    loadClassContext();
  }, [currentUser?.id, selectedClassId]);

  useEffect(() => {
    if (!currentUser?.id || !selectedQuizId) {
      setQuizDetail(null);
      setQuizAttempts([]);
      return;
    }

    const loadQuizContext = async () => {
      try {
        const detail = await getQuizDetail(selectedQuizId, currentUser.id);
        setQuizDetail(detail);
        if (isTutor) {
          const rows = await getQuizAttempts(selectedQuizId, currentUser.id);
          setQuizAttempts(rows);
          
          // If we are currently looking at a scorebook, refresh it for the new quiz
          if (result?.command === "show students") {
             runCommand("show students", { mode: "scorebook", classId: selectedClassId, quizId: selectedQuizId });
          }
        } else {
          setQuizAttempts([]);
          const nextAnswers = {};
          (detail.exercise_payload || []).forEach((_, index) => {
            nextAnswers[index + 1] = "";
          });
          if (detail.attempt?.submission_payload?.answers) {
            detail.attempt.submission_payload.answers.forEach((entry) => {
              nextAnswers[entry.question_id] = entry.answer_text;
            });
          }
          setQuizAnswers(nextAnswers);
        }
      } catch (error) {
        setBanner(error.message);
      }
    };

    loadQuizContext();
  }, [currentUser?.id, selectedQuizId, isTutor]);

  const quickMetrics = useMemo(() => {
    if (!result?.data) {
      return [{ label: "Start Here", value: "help" }];
    }

    const data = result.data;
    if (result.command === "check grammar") {
      return [
        { label: "Sentences", value: data.sentence_count || 0 },
        { label: "Grammar", value: data.grammar_errors?.length || 0 },
        { label: "Semantic", value: data.semantic_warnings?.length || 0 },
      ];
    }


    if (result.command === "generate") {
      return [
        { label: "Exercises", value: data.items?.length || 0 },
        { label: "Features", value: data.features?.length || 0 },
        { label: "Mode", value: "Playground" },
      ];
    }

    if (result.command === "create quiz") {
      return [
        { label: "Quiz ID", value: data.quiz_id || "—" },
        { label: "Exercises", value: data.exercise_count || 0 },
        { label: "Class", value: data.class_id || "—" },
      ];
    }

    if (result.command === "submit answers") {
      return [
        { label: "Score", value: `${data.score || 0}/${data.max_score || 0}` },
        { label: "Status", value: data.status || "—" },
        { label: "Reviewed", value: data.item_results?.length || 0 },
      ];
    }

    if (result.command === "show students") {
      return [
        { label: "Quiz", value: data.quiz_id || "—" },
        { label: "Matched", value: data.matched_rows || 0 },
        { label: "Total", value: data.total_rows || 0 },
      ];
    }

    if (result.command === "revision plan") {
      return [
        { label: "Checked Runs", value: data.summary?.reviewed_submissions || 0 },
        { label: "Tracked Issues", value: data.summary?.tracked_issues || 0 },
        { label: "Main Focus", value: data.summary?.main_focus || "Balanced" },
      ];
    }

    if (result.command === "history") {
      return [
        { label: "History", value: data.total_commands || 0 },
        { label: "Recent", value: data.entries?.length || 0 },
        { label: "Mode", value: "Timeline" },
      ];
    }

    if (result.command === "help") {
      const stats = data.pipeline_summary?.knowledge_stats || {};
      return [
        { label: "Commands", value: data.commands?.length || 0 },
        { label: "Imported Packs", value: stats.imported_sources || 0 },
        { label: "Rules", value: stats.phrase_index_entries || 0 },
      ];
    }

    return [
      { label: "Status", value: result.success ? "Ready" : "Invalid" },
      { label: "Command", value: result.command || "Unknown" },
      { label: "Mode", value: activeView },
    ];
  }, [result, activeView]);

  const deriveContext = () => {
    if (activeView === "classes" && tutorQuizAction === "scorebook") {
      return { mode: "scorebook", classId: selectedClassId, quizId: selectedQuizId };
    }
    if (activeView === "classes" && selectedQuizId) {
      return { mode: "quiz", classId: selectedClassId, quizId: selectedQuizId };
    }
    if (activeView === "classes") {
      return { mode: "class", classId: selectedClassId };
    }
    return { mode: "playground", classId: selectedClassId, quizId: selectedQuizId };
  };

  const refreshClassContext = async () => {
    if (!currentUser?.id) {
      return;
    }
    const nextClasses = await listClasses(currentUser.id);
    setClasses(nextClasses);
    if (selectedClassId) {
      const detail = await getClassDetail(selectedClassId, currentUser.id);
      const quizzes = await listClassQuizzes(selectedClassId, currentUser.id);
      setClassDetail(detail);
      setClassQuizzes(quizzes);
    }
    if (selectedQuizId) {
      const detail = await getQuizDetail(selectedQuizId, currentUser.id);
      setQuizDetail(detail);
      if (isTutor) {
        const rows = await getQuizAttempts(selectedQuizId, currentUser.id);
        setQuizAttempts(rows);
      }
    }
  };

  const runCommand = async (value, overrideContext = null) => {
    if (!currentUser?.id) {
      setBanner("Please log in first.");
      navigate("/login", { replace: true });
      return;
    }

    // Normalise: collapse multiple lines that each start with the same DSL command
    // to prevent accidental multi-command submissions from the textarea.
    const trimmedValue = value.trim();

    setLoading(true);
    setBanner("");
    setSubmittedInput(trimmedValue);
    setResult(null);

    const response = await executeDslCommand(trimmedValue, currentUser.id, overrideContext || deriveContext());
    updateActivity();

    if (!response.success && response.command === "auth_required") {
      setBanner(response.message);
      navigate("/login", { replace: true });
      setLoading(false);
      return;
    }

    setResult(response);
    if (response.success && response.command === "generate") {
      setPlaygroundExercises(response);
    }
    setLoading(false);

    if (response.success && ["create quiz", "submit answers", "show students"].includes(response.command)) {
      try {
        await refreshClassContext();
      } catch (error) {
        setBanner(error.message);
      }
    }
    if (response.success && response.command === "create quiz" && response.data?.quiz_id) {
      setSelectedQuizId(response.data.quiz_id);
      setTutorQuizAction("preview");
    }
  };

  // Called when the user clicks a suggestion chip in the error panel.
  // Replace the input with the suggestion (don't append) and immediately run it.
  const handleApplySuggestion = (suggestion) => {
    const clean = String(suggestion || "").trim();
    if (!clean) return;
    setInput(clean);
    runCommand(clean);
  };

  const handleLogout = async () => {
    if (currentUser?.id) {
      await logoutCurrentUser(currentUser.id);
    }
    setCurrentUser(null);
    setInput(DEFAULT_COMMAND);
    setSubmittedInput("");
    setResult(null);
    setBanner("");
    setClasses([]);
    setSelectedClassId(null);
    setClassDetail(null);
    setClassQuizzes([]);
    setSelectedQuizId(null);
    setQuizDetail(null);
    setQuizAttempts([]);
    setQuizAnswers({});
    navigate("/login", { replace: true });
  };

  const handleCreateClass = async (event) => {
    event.preventDefault();
    if (!className.trim() || !currentUser?.id) {
      return;
    }
    try {
      const created = await createClass(className.trim(), currentUser.id);
      setClassName("");
      setClasses((current) => [created, ...current]);
      setSelectedClassId(created.id);
      setBanner(`Class "${created.name}" created successfully.`);
    } catch (error) {
      setBanner(error.message);
    }
  };

  const handleJoinClass = async (event) => {
    event.preventDefault();
    if (!joinCode.trim() || !currentUser?.id) {
      return;
    }
    try {
      const joined = await joinClass(joinCode.trim(), currentUser.id);
      setJoinCode("");
      setClasses((current) => [joined, ...current.filter((entry) => entry.id !== joined.id)]);
      setSelectedClassId(joined.id);
      setBanner(`Joined ${joined.name}.`);
    } catch (error) {
      setBanner(error.message);
    }
  };

  const tutorCreateQuizCommand = `create quiz "${quizBuilder.title.replace(/"/g, "'")}" with ${quizBuilder.count} exercises with ${quizBuilder.features}`;

  const submitQuizCommand = useMemo(() => {
    if (!selectedQuizId || !quizDetail?.exercise_payload?.length) {
      return "";
    }
    const parts = quizDetail.exercise_payload.map((_, index) => {
      const answerText = sanitizeAnswerForDsl(quizAnswers[index + 1] || "");
      return `${index + 1} = "${answerText}"`;
    });
    return `submit answers for quiz ${selectedQuizId} { ${parts.join(" ; ")} }`;
  }, [quizAnswers, quizDetail?.exercise_payload, selectedQuizId]);

  const viewButtons = isTutor
    ? [
        { key: "playground", label: "Playground", icon: Sparkles },
        { key: "classes", label: "Classes & Quizzes", icon: Users },
      ]
    : [
        { key: "playground", label: "Playground", icon: Sparkles },
        { key: "classes", label: "Classes", icon: Users },
        { key: "study", label: "My Study", icon: BookOpen },
      ];

  const isPlaygroundView = activeView === "playground";
  const canUseDslInput =
    isPlaygroundView ||
    (activeView === "classes" && (isTutor || (Boolean(selectedQuizId) && Boolean(quizDetail) && !quizDetail.attempt)));
  const panelResult = result;
  const panelSubmittedInput = submittedInput;

  useEffect(() => {
    const previousView = previousViewRef.current;

    if (previousView === "playground" && activeView !== "playground") {
      playgroundSnapshotRef.current = {
        input,
        submittedInput,
        result,
        playgroundExercises,
      };
      setResult(null);
      setSubmittedInput("");
      setInput("");
    }

    if (previousView !== "playground" && activeView === "playground") {
      const snapshot = playgroundSnapshotRef.current;
      setInput(snapshot.input);
      setSubmittedInput(snapshot.submittedInput);
      setResult(snapshot.result);
      setPlaygroundExercises(snapshot.playgroundExercises);
    }

    previousViewRef.current = activeView;
  }, [activeView, input, submittedInput, result, playgroundExercises]);

  useEffect(() => {
    if (
      activeView === "classes" &&
      !isTutor &&
      selectedQuizId &&
      quizDetail &&
      !quizDetail.attempt &&
      submitQuizCommand
    ) {
      const isNew = submitQuizCommand !== input;
      setInput(submitQuizCommand);
      
      if (isNew && submitQuizCommand.includes('="')) {
        const el = document.querySelector('.dsl-textarea');
        if (el) {
          el.style.transition = 'none';
          el.style.backgroundColor = 'rgba(255, 51, 102, 0.1)';
          setTimeout(() => {
            el.style.transition = 'background-color 0.8s ease-out';
            el.style.backgroundColor = '';
          }, 50);
        }
      }
    }
  }, [activeView, isTutor, selectedQuizId, quizDetail, submitQuizCommand]);

  return (
    <div className="workspace-page">
      <WorkspaceNavbar currentUser={currentUser} onLogout={handleLogout} />

      <main className="workspace-page__body" style={{ position: "relative", zIndex: 1 }}>
        <img
          src={checkerbg}
          alt="background"
          className="absolute pointer-events-none"
          style={{
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            zIndex: -1,
          }}
        />
        <section className="workspace-shell">
          <div className="workspace-shell__left">
            <div className="input-panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.75rem" }}>
                <div>
                  <p className="master-box__eyebrow">Workspace</p>
                  <h1 style={{ fontSize: "clamp(2rem, 3vw, 3.2rem)", lineHeight: 1, marginBottom: "0.55rem" }}>
                    DSL Input
                  </h1>
                  {selectedQuizId && (
                    <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
                      <span className="lookup-chip lookup-chip--active" style={{ fontSize: "0.75rem", padding: "4px 10px" }}>
                        Active Context: Quiz #{selectedQuizId}
                      </span>
                    </div>
                  )}
                </div>

                {canUseDslInput ? (
                  <button
                    type="button"
                    onClick={() => runCommand(input)}
                    disabled={loading}
                    className="hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[1px_1px_0px_0px_#191A23]"
                    style={{
                      backgroundColor: "#B9FF66",
                      color: "#191A23",
                      fontWeight: "bold",
                      fontSize: "1rem",
                      padding: "10px 24px",
                      borderRadius: "8px",
                      border: "2px solid #191A23",
                      boxShadow: "3px 3px 0px 0px #191A23",
                      cursor: loading ? "not-allowed" : "pointer",
                      transition: "all 0.2s",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      height: "fit-content",
                    }}
                  >
                    <SendHorizontal size={16} />
                    {loading ? "Running..." : (input.trim().toLowerCase().startsWith("submit answers") ? "Submit Quiz" : "Run Command")}
                  </button>
                ) : null}
              </div>

              <div className="chip-row" style={{ marginBottom: "1rem" }}>
                {viewButtons.map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    type="button"
                    className={`lookup-chip lookup-chip--button ${activeView === key ? "lookup-chip--active" : ""}`}
                    onClick={() => setActiveView(key)}
                  >
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
              </div>

              {/* Suggestions removed as requested */}

              {activeView === "classes" ? (
                <div className="dashboard-list" style={{ marginBottom: "1rem" }}>
                  {isTutor ? (
                    <form className="dashboard-list__item" onSubmit={handleCreateClass}>
                      <h3>Create a class</h3>
                      <input
                        value={className}
                        onChange={(event) => setClassName(event.target.value)}
                        placeholder="Grammar Clinic A"
                        className="dsl-textarea"
                        style={{ minHeight: "auto", height: "56px", marginTop: "0.75rem" }}
                      />
                      <button type="submit" className="suggestion-cta" style={{ marginTop: "0.8rem" }}>
                        <PlusCircle size={16} />
                        Create Class
                      </button>
                    </form>
                  ) : (
                    <form className="dashboard-list__item" onSubmit={handleJoinClass}>
                      <h3>Join a class</h3>
                      <input
                        value={joinCode}
                        onChange={(event) => setJoinCode(event.target.value)}
                        placeholder="Join code"
                        className="dsl-textarea"
                        style={{ minHeight: "auto", height: "56px", marginTop: "0.75rem" }}
                      />
                      <button type="submit" className="suggestion-cta" style={{ marginTop: "0.8rem" }}>
                        <Users size={16} />
                        Join Class
                      </button>
                    </form>
                  )}

                  <article className="dashboard-list__item">
                    <h3>Your classes</h3>
                    <div className="chip-row" style={{ marginTop: "0.75rem" }}>
                      {classes.length ? (
                        classes.map((entry) => (
                          <button
                            key={entry.id}
                            type="button"
                            className={`lookup-chip lookup-chip--button ${selectedClassId === entry.id ? "lookup-chip--active" : ""}`}
                            onClick={() => setSelectedClassId(entry.id)}
                            style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", padding: "8px 16px", height: "auto" }}
                          >
                            <span style={{ fontSize: "0.95rem", fontWeight: "bold" }}>{entry.name}</span>
                            <span style={{ fontSize: "0.7rem", opacity: 0.6 }}>ID: #{entry.id}</span>
                          </button>
                        ))
                      ) : (
                        <span className="lookup-chip lookup-chip--soft">No classes yet</span>
                      )}
                    </div>
                  </article>

                  {classDetail ? (
                    <article className="dashboard-list__item">
                      <div className="dashboard-list__heading">
                        <h3>{classDetail.name}</h3>
                        <span>{classDetail.tutor_display_name}</span>
                      </div>
                      <p>Roster: {classDetail.roster_count} student(s) | Quizzes: {classDetail.quiz_count}</p>
                      {isTutor && classDetail.join_code ? (
                        <div className="bad-input-box" style={{ marginTop: "0.75rem", padding: "0.5rem 0.8rem" }}>
                          <code>Join code: {classDetail.join_code}</code>
                        </div>
                      ) : null}
                      <div className="chip-row" style={{ marginTop: "0.75rem" }}>
                        {classQuizzes.length ? (
                          classQuizzes.map((quiz) => (
                            <div 
                              key={quiz.id} 
                              className={`dashboard-list__item ${String(selectedQuizId) === String(quiz.id) ? "border-black" : ""}`}
                              style={{ 
                                width: "100%", 
                                padding: "1.25rem", 
                                cursor: "pointer", 
                                transition: "all 0.2s",
                                backgroundColor: String(selectedQuizId) === String(quiz.id) ? "#B9FF66" : "#fff",
                                boxShadow: String(selectedQuizId) === String(quiz.id) ? "5px 5px 0px 0px #191A23" : "none",
                                border: String(selectedQuizId) === String(quiz.id) ? "2px solid #191A23" : "1px solid #E5E7EB",
                                transform: String(selectedQuizId) === String(quiz.id) ? "translate(-2px, -2px)" : "none"
                              }}
                              onClick={() => {
                                setSelectedQuizId(quiz.id);
                                if (isTutor) {
                                  setTutorQuizAction("scorebook");
                                  setBanner(`Active Selection: Quiz #${quiz.id}`);
                                }
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                <div>
                                  <h4 style={{ fontSize: "1.1rem" }}>{quiz.title} <span style={{ fontSize: "0.75rem", opacity: 0.5, fontWeight: "normal" }}>ID: #{quiz.id}</span></h4>
                                  <p style={{ fontSize: "0.85rem", color: "#6B7280" }}>{quiz.feature_expr_text}</p>
                                </div>
                                <div className="chip-row">
                                  {/* Buttons removed for pure DSL workflow */}
                                </div>
                              </div>
                            </div>
                          ))
                        ) : (
                          <span className="lookup-chip lookup-chip--soft">No quizzes yet</span>
                        )}
                      </div>
                    </article>
                  ) : null}

                  {isTutor && selectedQuizId && quizDetail && tutorQuizAction === "preview" ? (
                    <article className="dashboard-list__item" style={{ border: "2px solid var(--ink)" }}>
                      <div className="dashboard-list__heading">
                        <h3>Preview: {quizDetail.title}</h3>
                        <span>{quizDetail.feature_expr_text}</span>
                      </div>
                      <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
                        {(quizDetail.exercise_payload || []).map((item, index) => (
                          <div key={item.id || index} className="bad-input-box" style={{ padding: "1rem", backgroundColor: "#fff" }}>
                            <p style={{ fontWeight: 600 }}>{index + 1}. {item.prompt}</p>
                            <p style={{ fontSize: "0.85rem", color: "#6B7280", marginTop: "0.4rem" }}>
                              Type: {item.type} | Difficulty: {item.difficulty} | Answer: <strong>{item.expected_answer}</strong>
                            </p>
                          </div>
                        ))}
                      </div>
                    </article>
                  ) : null}


                  {!isTutor && quizDetail ? (
                    <article className="dashboard-list__item">
                      <div className="dashboard-list__heading">
                        <h3>{quizDetail.title}</h3>
                        <span>{quizDetail.feature_expr_text}</span>
                      </div>

                      {quizDetail.attempt ? (
                        <div style={{ marginTop: "1rem" }}>
                          <div className="auth-banner" style={{ backgroundColor: "#F3F4F6", color: "#374151", marginBottom: "1.5rem", border: "1px solid #D1D5DB" }}>
                            You have already submitted this quiz. Results are shown below.
                          </div>
                          <ResultTemplates 
                            result={{ 
                              success: true, 
                              command: "submit answers", 
                              data: quizDetail.attempt.submission_payload.grading 
                            }} 
                          />
                        </div>
                      ) : (
                        <>
                          {(quizDetail.exercise_payload || []).map((item, index) => (
                            <div key={item.id || index} style={{ marginTop: "0.85rem" }}>
                              <p style={{ fontWeight: 600 }}>{index + 1}. {item.prompt}</p>
                              <textarea
                                className="dsl-textarea"
                                style={{ minHeight: "88px", marginTop: "0.4rem" }}
                                value={quizAnswers[index + 1] || ""}
                                onChange={(event) =>
                                  setQuizAnswers((current) => ({ ...current, [index + 1]: event.target.value }))
                                }
                                placeholder="Write your answer here"
                              />
                            </div>
                          ))}
                          <div 
                            className="bad-input-box" 
                            style={{ 
                              marginTop: "1.25rem", 
                              padding: "0.8rem 1rem", 
                              backgroundColor: "#FFF5F7",
                              border: "2px dashed #FF3366",
                              position: "relative",
                              overflow: "hidden"
                            }}
                          >
                            <div style={{ 
                              position: "absolute", 
                              top: "6px", 
                              right: "8px", 
                              display: "flex", 
                              alignItems: "center", 
                              gap: "4px",
                              fontSize: "0.65rem",
                              fontWeight: "bold",
                              color: "#FF3366",
                              textTransform: "uppercase",
                              letterSpacing: "0.05em"
                            }}>
                              <Sparkles size={10} />
                              Live DSL Sync
                            </div>
                            <code style={{ color: "#FF3366", wordBreak: "break-all" }}>
                              {submitQuizCommand || "Complete the quiz to build the submit command."}
                            </code>
                          </div>
                          
                          <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "10px" }}>
                            <div className="animate-pulse" style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#FF3366" }}></div>
                            <p style={{ fontSize: "0.85rem", color: "#6B7280", margin: 0 }}>
                              The command above is synced to your <strong>DSL Input</strong> workspace. Click <strong>Submit Quiz</strong> at the top to finish.
                            </p>
                          </div>
                        </>
                      )}
                    </article>
                  ) : null}
                </div>
              ) : null}

              {activeView === "study" && !isTutor ? (
                <div className="dashboard-list" style={{ marginBottom: "1rem" }}>
                  <article className="dashboard-list__item">
                    <h3>Your Quiz Scores</h3>
                    <p>Track your progress in "{classDetail?.name || "the selected class"}".</p>
                    
                    {classQuizzes.length ? (
                      <>
                        <div style={{ display: "grid", gap: "0.75rem", marginTop: "1rem" }}>
                          {classQuizzes.map((quiz) => (
                            <div 
                              key={quiz.id} 
                              className="bad-input-box cursor-pointer hover:border-black"
                              style={{
                                padding: "1rem",
                                borderRadius: "12px",
                                backgroundColor: String(selectedQuizId) === String(quiz.id) ? "#B9FF66" : "#FFFFFF",
                                border: String(selectedQuizId) === String(quiz.id) ? "2px solid #191A23" : undefined,
                                boxShadow: String(selectedQuizId) === String(quiz.id) ? "3px 3px 0px 0px #191A23" : "none",
                                color: "#191A23",
                              }}
                              onClick={() => {
                                setSelectedQuizId(quiz.id);
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div>
                                  <strong style={{ display: "block", fontSize: "1rem" }}>{quiz.title}</strong>
                                  <span style={{ fontSize: "0.85rem", color: "#6B7280" }}>{quiz.feature_expr_text}</span>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                  {quiz.attempt_status === "submitted" ? (
                                    <span style={{ color: "#059669", fontWeight: "bold", fontSize: "1.1rem" }}>
                                      {quiz.score}/{quiz.max_score}
                                    </span>
                                  ) : (
                                    <span style={{ color: "#D1D5DB", fontStyle: "italic" }}>Not started</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>

                        {selectedQuizId && (
                          <div style={{ marginTop: "2rem" }}>
                            <article className="dashboard-list__item" style={{ border: "2px solid var(--ink)" }}>
                              <div className="dashboard-list__heading">
                                <h3>Quiz Detail & Feedback</h3>
                                {quizDetail ? (
                                  <span>{quizDetail.feature_expr_text}</span>
                                ) : (
                                  <div style={{ height: "1rem", width: "8rem", backgroundColor: "rgba(0,0,0,0.05)", borderRadius: "4px" }} className="animate-pulse"></div>
                                )}
                              </div>
                              {renderQuizResults(quizDetail, quizAttempts)}
                            </article>
                          </div>
                        )}
                      </>
                    ) : (
                      <p style={{ marginTop: "1rem", fontStyle: "italic", color: "#6B7280" }}>No quizzes assigned yet.</p>
                    )}
                  </article>
                </div>
              ) : null}

                {canUseDslInput ? (
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  className="dsl-textarea"
                  placeholder={
                    activeView === "classes" && !isTutor
                      ? 'submit answers for quiz ... { 1 = "..." ; 2 = "..." }'
                      : "Type your DSL command here… (Enter to run)"
                  }
                  onKeyDown={(event) => {
                    // Plain Enter (without Shift) submits the command so the
                    // textarea stays single-line and avoids accidental multi-line inputs.
                    if (event.key === "Enter" && !event.shiftKey && !loading) {
                      event.preventDefault();
                      runCommand(input);
                    }
                  }}
                />
              ) : null}

              {banner ? <div className="auth-banner auth-banner--error">{banner}</div> : null}

              {isPlaygroundView && playgroundExercises?.data?.items?.length ? (
                <div className="dashboard-list" style={{ marginTop: "1.5rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <h3 style={{ fontSize: "1.2rem", fontWeight: "bold" }}>Playground Exercises</h3>
                    <button 
                      type="button" 
                      onClick={() => setPlaygroundExercises(null)}
                      className="secondary-command"
                      style={{ fontSize: "0.88rem", padding: "0.55rem 1rem" }}
                    >
                      <Eraser size={14} />
                      Clear
                    </button>
                  </div>
                  <p style={{ marginBottom: "0.75rem", color: "rgba(25, 26, 35, 0.7)" }}>
                    Click an exercise below to load it into the input box. Check your grammar on the right!
                  </p>
                  {playgroundExercises?.data?.items?.map((item, index) => (
                    <article 
                      key={item.id || index} 
                      className="dashboard-list__item cursor-pointer hover:border-black hover:shadow-sm"
                      onClick={() => {
                        let textToSolve = item.prompt;
                        if (textToSolve.toLowerCase().startsWith("fill in the missing")) {
                          textToSolve = textToSolve.split(":").slice(1).join(":").trim();
                        }
                        if (textToSolve.toLowerCase().startsWith("rewrite")) {
                          textToSolve = textToSolve.split(":").slice(1).join(":").trim();
                        }
                        setInput(`check grammar ${textToSolve}`);
                      }}
                    >
                      <div className="dashboard-list__heading">
                        <strong>{index + 1}. {item.type?.replace(/_/g, " ") || "exercise"}</strong>
                        <span>{item.difficulty}</span>
                      </div>
                      <div className="bad-input-box" style={{ marginTop: "0.5rem", padding: "0.5rem" }}>
                        <code>{item.prompt}</code>
                      </div>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="workspace-shell__right">
            <div className="response-header" style={{ backgroundColor: "#B9FF66" }}>
              <h2 style={{ fontSize: "2rem", color: "#191A23", marginBottom: 0 }}>
                {formatPanelTitle(panelResult?.command)}
              </h2>
            </div>
            <div style={{ padding: "1.5rem", overflowY: "auto", flex: 1 }}>
              <ResultTemplates 
                result={panelResult} 
                submittedInput={panelSubmittedInput}
                onApplySuggestion={handleApplySuggestion}
                onRunCommand={(cmd, ctx) => {
                  setInput(cmd);
                  runCommand(cmd, ctx);
                }}
                quizDetail={quizDetail}
                quizAttempts={quizAttempts}
                questionStats={questionStats}
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
