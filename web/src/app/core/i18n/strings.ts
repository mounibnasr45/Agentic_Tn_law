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

  // --- status ---
  statusTitle: string;
  refresh: string;
  database: string;
  encoder: string;
  indexedExtracts: string;
  modelLoaded: string;
  status: string;

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

  statusTitle: 'État du service',
  refresh: 'Actualiser',
  database: 'Base de données',
  encoder: 'Encodeur',
  indexedExtracts: 'Extraits indexés',
  modelLoaded: 'Modèle chargé',
  status: 'Statut',

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

  statusTitle: 'Service status',
  refresh: 'Refresh',
  database: 'Database',
  encoder: 'Encoder',
  indexedExtracts: 'Indexed extracts',
  modelLoaded: 'Model loaded',
  status: 'Status',

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

  sessionExpired: 'Session expired. Please sign in again.',
  invalidRequest: 'Invalid request.',
  tooManyRequests: 'Too many requests. Try again shortly.',
};

export const STRINGS: Record<'fr' | 'en', Strings> = { fr, en };
