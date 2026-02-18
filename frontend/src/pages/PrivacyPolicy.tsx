import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Logo } from '../components/brand/Logo'

const PrivacyPolicy = () => {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b border-gray-200/50 bg-white/80 backdrop-blur-xl dark:border-slate-800/50 dark:bg-slate-950/80">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="group">
              <Logo className="group-hover:scale-105 transition-all" textClassName="text-base sm:text-lg" />
            </Link>
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to home
            </Link>
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-2">
          Privacy Policy
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400 mb-10">
          Last updated: February 2026
        </p>

        <div className="prose prose-slate dark:prose-invert max-w-none space-y-8 text-gray-700 dark:text-slate-300 leading-relaxed">
          <p>
            ScholarHub ("we", "our", or "us") is committed to protecting the privacy of our users.
            This Privacy Policy explains how we collect, use, and safeguard your information when
            you use our collaborative research platform at scholarhub.space.
          </p>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              1. Information We Collect
            </h2>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Account Information
            </h3>
            <p>
              When you create an account, we collect your name, email address, and password
              (stored in hashed form). If you sign in through a third-party provider (e.g., Google),
              we receive the profile information you authorize.
            </p>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Research Data
            </h3>
            <p>
              We store the content you create on ScholarHub, including projects, documents, notes,
              discussion messages, references, and annotations. This data is yours and is stored
              solely to provide you with the service.
            </p>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Usage Data
            </h3>
            <p>
              We collect anonymized usage information such as pages visited, features used, and
              general interaction patterns. This helps us understand how the platform is used and
              where we can improve.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              2. How We Use Your Information
            </h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Providing the service:</strong> Your data is used to operate ScholarHub,
                including collaborative editing, paper discovery, reference management, and
                project organization.
              </li>
              <li>
                <strong>AI features:</strong> When you use AI-powered features (such as the discussion
                assistant, writing suggestions, or paper recommendations), relevant context from
                your project may be sent to AI providers to generate responses. See Section 4 for details.
              </li>
              <li>
                <strong>Improving the platform:</strong> Aggregated, anonymized usage data helps us
                prioritize features and fix issues.
              </li>
              <li>
                <strong>Communication:</strong> We may send you service-related emails such as
                account verification, password resets, and important platform updates.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              3. Data Storage and Security
            </h2>
            <p>
              Your data is stored in PostgreSQL databases with encryption at rest. Our infrastructure
              is hosted on secure servers with access restricted to authorized personnel only. We use
              industry-standard security practices including encrypted connections (TLS/SSL),
              hashed passwords, and regular security reviews.
            </p>
            <p className="mt-3">
              While we take reasonable measures to protect your data, no method of electronic storage
              or transmission is 100% secure. We encourage you to use strong, unique passwords for
              your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              4. Third-Party Services
            </h2>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              AI Providers
            </h3>
            <p>
              ScholarHub uses AI models through the OpenAI API and OpenRouter to power features
              like the discussion assistant, writing suggestions, and paper analysis. When you use
              these features, relevant context (such as your question and related project content) is
              sent to the AI provider to generate a response. We do not send your entire account data
              -- only the minimum context needed for the specific request. Please review the privacy
              policies of{' '}
              <a href="https://openai.com/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 hover:underline">OpenAI</a>
              {' '}and{' '}
              <a href="https://openrouter.ai/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 hover:underline">OpenRouter</a>
              {' '}for information on how they handle data.
            </p>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Zotero Integration
            </h3>
            <p>
              If you connect your Zotero account, we access your Zotero library data through their
              API to import references. We store a copy of the imported references in ScholarHub but
              do not modify your Zotero library.
            </p>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Academic Database APIs
            </h3>
            <p>
              Paper discovery queries are sent to external academic databases (such as Semantic
              Scholar, OpenAlex, PubMed, CrossRef, and CORE) to retrieve search results. These
              queries contain your search terms but not your personal information.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              5. Your Rights
            </h2>
            <p>You have the right to:</p>
            <ul className="list-disc pl-6 space-y-2 mt-2">
              <li>
                <strong>Access</strong> the personal data we hold about you.
              </li>
              <li>
                <strong>Correct</strong> inaccurate or incomplete data.
              </li>
              <li>
                <strong>Delete</strong> your account and associated data. Upon request, we will
                permanently delete your data within 30 days.
              </li>
              <li>
                <strong>Export</strong> your research data in standard formats.
              </li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, contact us at{' '}
              <a href="mailto:support@scholarhub.space" className="text-indigo-600 dark:text-indigo-400 hover:underline">
                support@scholarhub.space
              </a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              6. Data Retention
            </h2>
            <p>
              We retain your data for as long as your account is active. If you delete your account,
              we will remove your personal data and research content within 30 days. Some anonymized,
              aggregated data (such as usage statistics) may be retained indefinitely as it cannot be
              linked back to you.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              7. Cookies
            </h2>
            <p>
              ScholarHub uses session cookies to keep you logged in and maintain your authentication
              state. These are essential cookies required for the platform to function. We do not use
              third-party tracking cookies or advertising cookies.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              8. Changes to This Policy
            </h2>
            <p>
              We may update this Privacy Policy from time to time. If we make significant changes,
              we will notify you by email or through a notice on the platform. Your continued use of
              ScholarHub after changes are posted constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              9. Contact
            </h2>
            <p>
              If you have any questions about this Privacy Policy or how we handle your data, please
              contact us at{' '}
              <a href="mailto:support@scholarhub.space" className="text-indigo-600 dark:text-indigo-400 hover:underline">
                support@scholarhub.space
              </a>.
            </p>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 dark:border-slate-800 py-8 px-4">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500 dark:text-slate-500">
          <p>&copy; {new Date().getFullYear()} ScholarHub. All rights reserved.</p>
          <div className="flex items-center gap-4">
            <Link to="/terms" className="hover:text-gray-900 dark:hover:text-white transition-colors">
              Terms of Service
            </Link>
            <Link to="/privacy" className="hover:text-gray-900 dark:hover:text-white transition-colors">
              Privacy Policy
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default PrivacyPolicy
