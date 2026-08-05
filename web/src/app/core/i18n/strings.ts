/**
 * Every user-visible string, in both languages.
 *
 * ONE FILE, NOT ONE PER FEATURE. A translation that lives next to its component is a
 * translation that gets forgotten when the other language is added — the failure mode is a
 * half-English page, which is worse than either language alone. Keeping both columns
 * side by side makes a missing translation visible while writing it, and `Strings` being a
 * type means the English object cannot compile while a key is absent.
 *
 * Material icon names (`logout`, `refresh`, `balance`) are NOT here: they are glyph
 * identifiers, not prose, and translating them would render nothing.
 */
export interface Strings {
  // --- shell ---
  brand: string;
  skipToContent: string;
  navChat: string;
  navSearch: string;
  navDocuments: string;
  navEvaluation: string;
  navStatus: string;
  navAdmin: string;
  mainNavLabel: string;
  openNavMenu: string;
  logout: string;
  languageToggle: string;
  themeLight: string;
  themeDark: string;
  themeSystem: string;

  // --- auth ---
  email: string;
  password: string;
  emailRequired: string;
  emailInvalid: string;
  passwordRequired: string;

  // --- landing ---
  landingKicker: string;
  landingTitle: string;
  landingLede: string;
  landingCtaPrimary: string;
  landingCtaSecondary: string;
  landingFeaturesLabel: string;
  landingFeature1Title: string;
  landingFeature1Body: string;
  landingFeature2Title: string;
  landingFeature2Body: string;
  landingFeature3Title: string;
  landingFeature3Body: string;
  landingFeature4Title: string;
  landingFeature4Body: string;
  landingCorpusTitle: string;
  landingCorpusLede: string;
  landingCorpusLoadFailed: string;
  landingPassagesIndexed: string;
  landingFooterCta: string;

  // --- auth (continued) ---
  signIn: string;
  signUp: string;
  noAccountYet: string;
  alreadyHaveAccount: string;
  loginTagline: string;

  // --- chat ---
  conversations: string;
  showConversations: string;
  askFirstQuestion: string;
  consultingTexts: string;
  notSent: string;
  retry: string;
  suggestion1: string;
  suggestion2: string;
  suggestion3: string;
  you: string;
  agentAuthor: string;
  copyAnswer: string;
  copied: string;
  emptyStateBody: string;
  disclaimer: string;
  sourceCited: string;
  sourcesCited: string;
  topSourcesCited: (total: number) => string;
  newConversation: string;
  noConversationsYet: string;
  composerPlaceholder: string;
  composerHint: string;
  send: string;
  preamble: string;
  regrounded: string;

  // --- agent trace ---
  agentReasoning: string;
  question: string;
  agentQuery: string;
  iterationsTooltip: string;
  regroundedTooltip: string;
  noSourceConsulted: string;

  // --- documents ---
  documentsTitle: string;
  documentsSubtitle: string;
  documentsLoadFailed: string;
  documentDisplayFailed: string;
  openInNewTab: string;
  download: string;
  downloadInstead: string;
  indexedPassages: string;

  // --- search ---
  searchTitle: string;
  query: string;
  queryPlaceholder: string;
  resultCount: string;
  fusionStrategy: string;
  noExtractMatches: string;
  weightHint: string;

  searchSubtitle: string;
  searchButton: string;
  serverWeightHint: string;

  // --- status ---
  statusTitle: string;
  refresh: string;
  database: string;
  encoder: string;
  indexedExtracts: string;
  modelLoaded: string;
  status: string;
  apiUnreachable: string;
  corpusNotIndexed: string;

  // --- evaluation ---
  evaluationTitle: string;
  loadingResults: string;
  evaluationUnavailable: string;
  goldenQuestions: string;
  configurationsCompared: string;

  // --- admin ---
  adminTitle: string;
  adminDropzone: string;
  adminDropzoneHint: string;
  adminIngestStarts: string;
  adminNoDocuments: string;
  adminReadFailed: string;
  adminRefresh: string;
  adminDocuments: string;
  adminFile: string;
  adminFragments: string;
  adminProgress: string;
  adminIndexedOn: string;
  adminIndexedFragments: string;
  adminEncoder: string;
  adminIntro: string;
  adminOr: string;
  adminChooseFile: string;
  adminDocumentsCount: string;

  // --- admin: users ---
  adminUsersTitle: string;
  adminUsersReadFailed: string;
  adminColEmail: string;
  adminColMessages: string;
  adminColSessions: string;
  adminColRole: string;
  adminColActions: string;
  adminRoleAdmin: string;
  adminRoleUser: string;
  adminGrantAdmin: string;
  adminRevokeAdmin: string;
  adminCannotRevokeSelf: string;

  // --- evaluation prose ---
  evalAblationTitle: string;
  evalMethod: string;
  evalBefore: string;
  evalAfter: string;
  evalConfiguration: string;
  evalArm: string;
  evalNoLlmJudge: string;
  evalArticleRelevance: string;
  evalThreshold: string;
  evalLimits: string;
  evalIndexedFragments: string;
  evalDeployedTooltip: string;
  evalGateTooltip: string;
  evalMrrTooltip: string;

  evalWhatMeasuring: string;
  evalTruncationFinding: string;
  evalCharacters: string;
  evalOfHit5: string;
  evalNoiseMargin: string;
  evalWeightIs1: string;
  evalWeightIs2: string;
  evalWeightIsStrategy: string;
  evalDeployed: string;
  evalDenseWins: string;
  evalDenseWinsBody: string;
  evalArticleLevelBody: string;
  evalNoJudgeBody: string;
  evalLimitsBody: string;

  // --- errors ---
  sessionExpired: string;
  invalidRequest: string;
  tooManyRequests: string;
}

const fr: Strings = {
  brand: 'Agent Juridique Tunisien',
  skipToContent: 'Aller au contenu',
  navChat: 'Discussion',
  navSearch: 'Recherche',
  navDocuments: 'Textes',
  navEvaluation: 'Évaluation',
  navStatus: 'État',
  navAdmin: 'Corpus',
  mainNavLabel: 'Navigation principale',
  openNavMenu: 'Ouvrir le menu de navigation',
  logout: 'Se déconnecter',
  languageToggle: 'Switch to English',
  themeLight: 'Thème clair — cliquer pour le thème sombre',
  themeDark: 'Thème sombre — cliquer pour suivre le système',
  themeSystem: 'Thème système — cliquer pour le thème clair',

  email: 'Email',
  password: 'Mot de passe',
  emailRequired: "L'email est requis.",
  emailInvalid: "Format d'email invalide.",
  passwordRequired: 'Le mot de passe est requis.',

  landingKicker: 'Agent juridique augmenté par recherche',
  landingTitle: 'Le droit tunisien, interrogé et cité avec précision',
  landingLede:
    "Un agent conversationnel qui répond exclusivement à partir des textes de loi indexés — jamais de mémoire. Recherche hybride (similarité vectorielle et recherche plein texte), citations vérifiables article par article, et qualité de récupération mesurée en continu sur un jeu de questions de référence.",
  landingCtaPrimary: 'Commencer gratuitement',
  landingCtaSecondary: "Voir l'agent en action",
  landingFeaturesLabel: 'Caractéristiques techniques',
  landingFeature1Title: 'Recherche hybride',
  landingFeature1Body:
    'Similarité vectorielle (pgvector) et recherche plein texte (Postgres, ts_rank_cd) fusionnées par pondération ou par rang réciproque — pas un index en mémoire, perdu au moindre redémarrage.',
  landingFeature2Title: 'Citations vérifiables',
  landingFeature2Body:
    "Chaque article cité a réellement été retrouvé par la recherche : une clé étrangère en base l'impose, ce qui exclut structurellement la citation inventée.",
  landingFeature3Title: 'Qualité mesurée',
  landingFeature3Body:
    "98,2 % de hit@5 sur un jeu de 56 questions de référence, recalculé à chaque changement et intégré comme condition de déploiement en CI.",
  landingFeature4Title: 'Relecture auto-corrective',
  landingFeature4Body:
    "Avant de répondre, l'agent relit son brouillon à la recherche de termes juridiques non définis dans les extraits retenus, et relance une recherche ciblée si nécessaire.",
  landingCorpusTitle: 'Le corpus indexé',
  landingCorpusLede:
    'Trois textes de référence du droit tunisien, à jour dans la base de recherche.',
  landingCorpusLoadFailed: 'Impossible de charger le corpus pour le moment.',
  landingPassagesIndexed: 'passages indexés',
  landingFooterCta: 'Créer un compte et poser une première question',

  signIn: 'Se connecter',
  signUp: "S'inscrire",
  noAccountYet: 'Pas encore de compte ?',
  alreadyHaveAccount: 'Déjà un compte ?',
  loginTagline:
    'Réponses ancrées dans la Constitution et le Code Pénal tunisiens, avec citations vérifiables.',

  conversations: 'Conversations',
  showConversations: 'Afficher les conversations',
  askFirstQuestion: 'Posez votre première question',
  consultingTexts: 'consulte les textes…',
  notSent: "Non envoyé — rien n'a été enregistré.",
  retry: 'Réessayer',
  suggestion1: 'Quelles sont les circonstances aggravantes du vol ?',
  suggestion2: 'Que dit la Constitution sur la liberté d’expression ?',
  suggestion3: "Que dit l'article 258 ?",
  you: 'Vous',
  agentAuthor: 'Agent juridique',
  copyAnswer: 'Copier la réponse',
  copied: 'Copié',
  emptyStateBody:
    "Les réponses sont ancrées dans la Constitution et le Code Pénal tunisiens, et citent les articles sur lesquels elles s'appuient.",
  disclaimer:
    'Réponses générées automatiquement à partir des textes indexés — ne constituent pas un conseil juridique.',
  sourceCited: 'source citée',
  sourcesCited: 'sources citées',
  topSourcesCited: (total) => `Top 5 sources citées (${total} au total)`,
  newConversation: 'Nouvelle conversation',
  noConversationsYet: "Aucune conversation pour l'instant.",
  composerPlaceholder: 'Posez votre question juridique…',
  composerHint: 'Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne',
  send: 'Envoyer',
  preamble: 'Préambule',
  regrounded: 'réancrée',

  agentReasoning: "Raisonnement de l'agent",
  question: 'Question',
  agentQuery: "Requête de l'agent",
  iterationsTooltip: "Appels d'outil utilisés sur le plafond configuré",
  regroundedTooltip:
    "Un terme technique n'était pas défini : l'agent a relancé une recherche",
  noSourceConsulted:
    "L'agent n'a interrogé aucune source pour cette réponse — probablement une question hors du périmètre indexé.",

  documentsTitle: 'Textes sources',
  documentsSubtitle:
    "Les documents que l'agent cite. Consultez-les ici pour vérifier une citation directement à la source.",
  documentsLoadFailed: 'Impossible de charger les textes sources.',
  documentDisplayFailed: "Impossible d'afficher ce document.",
  openInNewTab: 'Ouvrir dans un nouvel onglet',
  download: 'Télécharger',
  downloadInstead: 'Télécharger à la place',
  indexedPassages: 'passages indexés',

  searchTitle: 'Explorateur de recherche',
  query: 'Requête',
  queryPlaceholder: "Que dit l'article 258 ?",
  resultCount: 'Nombre de résultats',
  fusionStrategy: 'Stratégie de fusion',
  noExtractMatches: 'Aucun extrait ne correspond à cette requête.',
  weightHint: '0.0 = dense seul · 1.0 = lexical seul',

  searchSubtitle:
    'Récupération seule, sans LLM — les extraits bruts que le retriever renvoie réellement, avec leurs scores.',
  searchButton: 'Rechercher',
  serverWeightHint:
    'Utiliser le poids lexical configuré côté serveur (0.0 — dense seul, le meilleur mesuré)',

  statusTitle: 'État du service',
  refresh: 'Actualiser',
  database: 'Base de données',
  encoder: 'Encodeur',
  indexedExtracts: 'Extraits indexés',
  modelLoaded: 'Modèle chargé',
  status: 'Statut',
  apiUnreachable: 'API injoignable — aucune réponse du service.',
  corpusNotIndexed: "Le corpus n'est pas indexé — l'agent ne peut rien citer. Lancez",

  evaluationTitle: 'Évaluation de la recherche',
  loadingResults: 'Chargement des résultats…',
  evaluationUnavailable: "Résultats d'évaluation indisponibles.",
  goldenQuestions: 'questions de référence',
  configurationsCompared: 'configurations comparées',

  adminTitle: 'Corpus juridique',
  adminDropzone: 'Glissez un PDF ici',
  adminDropzoneHint: "L'indexation démarre une fois l'envoi terminé.",
  adminIngestStarts: "L'indexation démarre une fois l'envoi terminé.",
  adminNoDocuments: 'Aucun document. Déposez un PDF pour commencer.',
  adminReadFailed: "Impossible de lire l'état du corpus.",
  adminRefresh: 'Rafraîchir',
  adminDocuments: 'Documents',
  adminFile: 'Fichier',
  adminFragments: 'Fragments',
  adminProgress: 'Progression',
  adminIndexedOn: 'Indexé le',
  adminIndexedFragments: 'fragments indexés',
  adminEncoder: 'encodeur',
  adminIntro:
    "Ajoutez un texte de loi au format PDF. Il est découpé par article, encodé, puis indexé — après quoi l'agent peut le citer.",
  adminOr: 'ou',
  adminChooseFile: 'Choisir un fichier',
  adminDocumentsCount: 'document(s)',

  adminUsersTitle: 'Utilisateurs',
  adminUsersReadFailed: 'Impossible de charger la liste des utilisateurs.',
  adminColEmail: 'Email',
  adminColMessages: 'Messages',
  adminColSessions: 'Sessions',
  adminColRole: 'Rôle',
  adminColActions: 'Actions',
  adminRoleAdmin: 'Administrateur',
  adminRoleUser: 'Utilisateur',
  adminGrantAdmin: 'Accorder les droits admin',
  adminRevokeAdmin: 'Retirer les droits admin',
  adminCannotRevokeSelf: 'Vous ne pouvez pas retirer vos propres droits admin',

  evalAblationTitle: 'Ablation : quelle configuration gagne ?',
  evalMethod: 'Méthode',
  evalBefore: 'Avant',
  evalAfter: 'Après',
  evalConfiguration: 'Configuration',
  evalArm: 'Bras',
  evalNoLlmJudge: 'Aucun juge LLM.',
  evalArticleRelevance: "Pertinence au niveau de l'article.",
  evalThreshold: 'Le seuil de régression tolère 3 points, pas zéro.',
  evalLimits: 'Limites assumées.',
  evalIndexedFragments: 'fragments indexés',
  evalDeployedTooltip: "C'est cette configuration qui est déployée",
  evalGateTooltip: 'La métrique qui bloque la CI',
  evalMrrTooltip: '1/rang — pénalise fortement la profondeur',

  evalWhatMeasuring: 'Ce que la mesure a trouvé',
  evalTruncationFinding: "L'encodeur tronquait silencieusement 38 % du corpus",
  evalCharacters: 'caractères',
  evalOfHit5: 'de hit@5, sans changer une ligne de logique de recherche.',
  evalNoiseMargin: '= 1 question (marge de bruit)',
  evalWeightIs1: 'Le poids',
  evalWeightIs2: 'est',
  evalWeightIsStrategy:
    'la stratégie : 0.0 = dense seul, 1.0 = lexical seul, entre les deux = hybride. Un seul axe produit les trois approches habituellement codées séparément.',
  evalDeployed: 'déployé',
  evalDenseWins: 'Le dense seul bat toutes les configurations hybrides',
  evalDenseWinsBody:
    "C'est donc le dense qui est déployé. Livrer « hybride » parce que le mot sonne mieux serait choisir un système moins bon pour un vocabulaire plus flatteur.",
  evalArticleLevelBody:
    "Un article long est réparti sur plusieurs fragments ; en retrouver un seul signifie que le bon texte de loi a été trouvé. Compter au niveau du fragment pénaliserait nos choix de découpage, pas le classement.",
  evalNoJudgeBody:
    "Le classement a de vraies métriques. Un juge LLM serait non déterministe, coûterait de l'argent à chaque exécution et ne pourrait pas bloquer une build — on ne fait pas échouer une CI sur un nombre qui fluctue.",
  evalLimitsBody:
    "56 questions, c'est peu : un écart de 0,05 vaut environ trois questions. Les questions à articles multiples, les négations et les renvois entre articles ne sont pas représentés.",

  sessionExpired: 'Session expirée. Veuillez vous reconnecter.',
  invalidRequest: 'Requête invalide.',
  tooManyRequests: 'Trop de requêtes. Réessayez dans un instant.',
};

const en: Strings = {
  // Kept in French: it is the product's name, and a name is not a string to translate.
  brand: 'Agent Juridique Tunisien',
  skipToContent: 'Skip to content',
  navChat: 'Chat',
  navSearch: 'Search',
  navDocuments: 'Texts',
  navEvaluation: 'Evaluation',
  navStatus: 'Status',
  navAdmin: 'Corpus',
  mainNavLabel: 'Main navigation',
  openNavMenu: 'Open navigation menu',
  logout: 'Sign out',
  languageToggle: 'Passer en français',
  themeLight: 'Light theme — click for dark',
  themeDark: 'Dark theme — click to follow the system',
  themeSystem: 'System theme — click for light',

  email: 'Email',
  password: 'Password',
  emailRequired: 'Email is required.',
  emailInvalid: 'Invalid email format.',
  passwordRequired: 'Password is required.',

  landingKicker: 'Retrieval-augmented legal agent',
  landingTitle: 'Tunisian law, queried and cited with precision',
  landingLede:
    'A conversational agent that answers only from the indexed legal texts — never from memory. Hybrid retrieval (vector similarity and full-text search), article-level verifiable citations, and retrieval quality measured continuously against a golden question set.',
  landingCtaPrimary: 'Get started for free',
  landingCtaSecondary: 'See the agent in action',
  landingFeaturesLabel: 'Technical highlights',
  landingFeature1Title: 'Hybrid retrieval',
  landingFeature1Body:
    'Vector similarity (pgvector) and full-text search (Postgres, ts_rank_cd) fused by weighted score or reciprocal rank — not an in-memory index, gone on the next restart.',
  landingFeature2Title: 'Verifiable citations',
  landingFeature2Body:
    'Every cited article was actually retrieved by the search: a database foreign key enforces it, which rules out a fabricated citation structurally, not by prompting.',
  landingFeature3Title: 'Measured quality',
  landingFeature3Body:
    '98.2% hit@5 on a 56-question golden set, re-measured on every change and gating every deploy in CI.',
  landingFeature4Title: 'Self-correcting review',
  landingFeature4Body:
    'Before answering, the agent re-reads its own draft for legal terms the retrieved excerpts never defined, and runs one more targeted search when it finds one.',
  landingCorpusTitle: 'The indexed corpus',
  landingCorpusLede: 'Three reference texts of Tunisian law, live in the search index.',
  landingCorpusLoadFailed: 'Could not load the corpus right now.',
  landingPassagesIndexed: 'indexed passages',
  landingFooterCta: 'Create an account and ask a first question',

  signIn: 'Sign in',
  signUp: 'Sign up',
  noAccountYet: 'No account yet?',
  alreadyHaveAccount: 'Already have an account?',
  loginTagline:
    'Answers grounded in the Tunisian Constitution and Penal Code, with verifiable citations.',

  conversations: 'Conversations',
  showConversations: 'Show conversations',
  askFirstQuestion: 'Ask your first question',
  consultingTexts: 'consulting the texts…',
  notSent: 'Not sent — nothing was saved.',
  retry: 'Retry',
  // Left in French on purpose: these are one-tap examples that get sent verbatim, and the
  // corpus is the French text of Tunisian law. An English example would demonstrate the
  // weaker retrieval path as the app's first impression.
  suggestion1: 'Quelles sont les circonstances aggravantes du vol ?',
  suggestion2: 'Que dit la Constitution sur la liberté d’expression ?',
  suggestion3: "Que dit l'article 258 ?",
  you: 'You',
  agentAuthor: 'Legal agent',
  copyAnswer: 'Copy answer',
  copied: 'Copied',
  emptyStateBody:
    'Answers are grounded in the Tunisian Constitution and Penal Code, and cite the articles they rely on.',
  disclaimer:
    'Answers are generated automatically from the indexed texts — they are not legal advice.',
  sourceCited: 'source cited',
  sourcesCited: 'sources cited',
  topSourcesCited: (total) => `Top 5 sources cited (${total} in total)`,
  newConversation: 'New conversation',
  noConversationsYet: 'No conversations yet.',
  composerPlaceholder: 'Ask your legal question…',
  composerHint: 'Enter to send · Shift+Enter for a new line',
  send: 'Send',
  preamble: 'Preamble',
  regrounded: 'regrounded',

  agentReasoning: 'Agent reasoning',
  question: 'Question',
  agentQuery: 'Agent query',
  iterationsTooltip: 'Tool calls used against the configured ceiling',
  regroundedTooltip: 'A term of art was undefined: the agent ran another search',
  noSourceConsulted:
    'The agent consulted no source for this answer — most likely a question outside the indexed corpus.',

  documentsTitle: 'Source texts',
  documentsSubtitle:
    'The documents the agent cites. Read them here to check a citation directly against its source.',
  documentsLoadFailed: 'Could not load the source texts.',
  documentDisplayFailed: 'Could not display this document.',
  openInNewTab: 'Open in a new tab',
  download: 'Download',
  downloadInstead: 'Download instead',
  indexedPassages: 'indexed passages',

  searchTitle: 'Search explorer',
  query: 'Query',
  queryPlaceholder: 'What does article 258 say?',
  resultCount: 'Number of results',
  fusionStrategy: 'Fusion strategy',
  noExtractMatches: 'No extract matches this query.',
  weightHint: '0.0 = dense only · 1.0 = lexical only',

  searchSubtitle:
    'Retrieval only, no LLM — the raw extracts the retriever actually returns, with their scores.',
  searchButton: 'Search',
  serverWeightHint:
    'Use the lexical weight configured server-side (0.0 — dense only, the best measured)',

  statusTitle: 'Service status',
  refresh: 'Refresh',
  database: 'Database',
  encoder: 'Encoder',
  indexedExtracts: 'Indexed extracts',
  modelLoaded: 'Model loaded',
  status: 'Status',
  apiUnreachable: 'API unreachable — no response from the service.',
  corpusNotIndexed: 'The corpus is not indexed — the agent has nothing to cite. Run',

  evaluationTitle: 'Retrieval evaluation',
  loadingResults: 'Loading results…',
  evaluationUnavailable: 'Evaluation results unavailable.',
  goldenQuestions: 'golden questions',
  configurationsCompared: 'configurations compared',

  adminTitle: 'Legal corpus',
  adminDropzone: 'Drop a PDF here',
  adminDropzoneHint: 'Indexing starts once the upload finishes.',
  adminIngestStarts: 'Indexing starts once the upload finishes.',
  adminNoDocuments: 'No documents. Drop a PDF to get started.',
  adminReadFailed: 'Could not read the corpus status.',
  adminRefresh: 'Refresh',
  adminDocuments: 'Documents',
  adminFile: 'File',
  adminFragments: 'Fragments',
  adminProgress: 'Progress',
  adminIndexedOn: 'Indexed on',
  adminIndexedFragments: 'indexed fragments',
  adminEncoder: 'encoder',
  adminIntro:
    'Add a legal text as a PDF. It is split by article, encoded, then indexed — after which the agent can cite it.',
  adminOr: 'or',
  adminChooseFile: 'Choose a file',
  adminDocumentsCount: 'document(s)',

  adminUsersTitle: 'Users',
  adminUsersReadFailed: 'Could not load the user list.',
  adminColEmail: 'Email',
  adminColMessages: 'Messages',
  adminColSessions: 'Sessions',
  adminColRole: 'Role',
  adminColActions: 'Actions',
  adminRoleAdmin: 'Administrator',
  adminRoleUser: 'User',
  adminGrantAdmin: 'Grant admin rights',
  adminRevokeAdmin: 'Revoke admin rights',
  adminCannotRevokeSelf: 'You cannot revoke your own admin rights',

  evalAblationTitle: 'Ablation: which configuration wins?',
  evalMethod: 'Method',
  evalBefore: 'Before',
  evalAfter: 'After',
  evalConfiguration: 'Configuration',
  evalArm: 'Arm',
  evalNoLlmJudge: 'No LLM judge.',
  evalArticleRelevance: 'Relevance at the article level.',
  evalThreshold: 'The regression threshold allows 3 points, not zero.',
  evalLimits: 'Acknowledged limits.',
  evalIndexedFragments: 'indexed fragments',
  evalDeployedTooltip: 'This is the configuration that is deployed',
  evalGateTooltip: 'The metric that blocks CI',
  evalMrrTooltip: '1/rank — penalises depth heavily',

  evalWhatMeasuring: 'What the measurement found',
  evalTruncationFinding: 'The encoder was silently truncating 38% of the corpus',
  evalCharacters: 'characters',
  evalOfHit5: 'of hit@5, without changing a line of retrieval logic.',
  evalNoiseMargin: '= 1 question (noise margin)',
  evalWeightIs1: 'The weight',
  evalWeightIs2: 'is',
  evalWeightIsStrategy:
    'the strategy: 0.0 = dense only, 1.0 = lexical only, in between = hybrid. A single axis produces all three approaches people usually hand-code separately.',
  evalDeployed: 'deployed',
  evalDenseWins: 'Dense alone beats every hybrid configuration',
  evalDenseWinsBody:
    'So dense is what ships. Shipping "hybrid" because the word sounds better would mean choosing a worse system for a more flattering vocabulary.',
  evalArticleLevelBody:
    'A long article is split across several fragments; retrieving any one of them means the right legal text was found. Counting at fragment level would penalise our chunking choices, not the ranking.',
  evalNoJudgeBody:
    'Ranking has real metrics. An LLM judge would be non-deterministic, cost money on every run, and could not gate a build — you do not fail CI on a number that fluctuates.',
  evalLimitsBody:
    '56 questions is few: a gap of 0.05 is worth about three questions. Multi-article questions, negations and cross-references between articles are not represented.',

  sessionExpired: 'Session expired. Please sign in again.',
  invalidRequest: 'Invalid request.',
  tooManyRequests: 'Too many requests. Try again shortly.',
};

export const STRINGS: Record<'fr' | 'en', Strings> = { fr, en };
