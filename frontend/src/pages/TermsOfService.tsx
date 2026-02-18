import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Logo } from '../components/brand/Logo'

const TermsOfService = () => {
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
          Terms of Service
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400 mb-10">
          Last updated: February 2026
        </p>

        <div className="prose prose-slate dark:prose-invert max-w-none space-y-8 text-gray-700 dark:text-slate-300 leading-relaxed">
          <p>
            Welcome to ScholarHub. By accessing or using our platform at scholarhub.space, you agree
            to be bound by these Terms of Service ("Terms"). Please read them carefully before using
            the service.
          </p>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              1. Acceptance of Terms
            </h2>
            <p>
              By creating an account or using ScholarHub, you agree to these Terms and our{' '}
              <Link to="/privacy" className="text-indigo-600 dark:text-indigo-400 hover:underline">
                Privacy Policy
              </Link>. If you do not agree, you may not use the service. If you are using ScholarHub
              on behalf of an organization, you represent that you have authority to bind that
              organization to these Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              2. Description of Service
            </h2>
            <p>
              ScholarHub is a collaborative academic research platform that provides:
            </p>
            <ul className="list-disc pl-6 space-y-2 mt-2">
              <li>LaTeX and rich-text document editing with real-time collaboration</li>
              <li>Paper discovery across multiple academic databases</li>
              <li>AI-powered research assistance (discussion, writing suggestions, paper analysis)</li>
              <li>Reference management with Zotero and BibTeX integration</li>
              <li>Project organization with task management and team collaboration</li>
              <li>Publication-ready manuscript export in multiple journal formats</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              3. User Accounts
            </h2>
            <p>
              You must be at least 16 years old to create an account. You are responsible for
              maintaining the confidentiality of your login credentials and for all activity that
              occurs under your account. You agree to notify us immediately if you suspect
              unauthorized access to your account.
            </p>
            <p className="mt-3">
              You must provide accurate and complete information when creating your account and keep
              it up to date.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              4. Acceptable Use
            </h2>
            <p>ScholarHub is designed for academic and research purposes. You agree not to:</p>
            <ul className="list-disc pl-6 space-y-2 mt-2">
              <li>Upload or share illegal, defamatory, or infringing content</li>
              <li>Use the platform to harass, abuse, or harm others</li>
              <li>Attempt to gain unauthorized access to other accounts or systems</li>
              <li>Abuse AI features (e.g., automated bulk requests, generating misleading academic content)</li>
              <li>Interfere with the operation of the platform or circumvent usage limits</li>
              <li>Use the service for any purpose that violates applicable laws or regulations</li>
            </ul>
            <p className="mt-3">
              We reserve the right to suspend or terminate accounts that violate these guidelines.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              5. Intellectual Property
            </h2>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Your Content
            </h3>
            <p>
              You retain full ownership of all research content you create on ScholarHub, including
              documents, notes, annotations, and discussion messages. By using the service, you grant
              us a limited license to store, display, and transmit your content solely to provide the
              service to you and your collaborators.
            </p>

            <h3 className="text-lg font-medium text-gray-900 dark:text-white mt-6 mb-2">
              Our Platform
            </h3>
            <p>
              ScholarHub and its underlying technology, design, and branding are the intellectual
              property of ScholarHub. You may not copy, modify, or reverse-engineer any part of the
              platform without our written permission.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              6. AI Features Disclaimer
            </h2>
            <p>
              ScholarHub provides AI-powered features including a research discussion assistant,
              writing suggestions, and paper analysis tools. These features are provided as aids to
              your research workflow.
            </p>
            <p className="mt-3">
              <strong>AI-generated content is not guaranteed to be accurate, complete, or
              error-free.</strong> You are solely responsible for reviewing, verifying, and validating
              any AI suggestions before including them in your work. AI outputs should not be treated
              as authoritative academic sources.
            </p>
            <p className="mt-3">
              When you use AI features, relevant context from your project is processed by third-party
              AI providers (see our{' '}
              <Link to="/privacy" className="text-indigo-600 dark:text-indigo-400 hover:underline">
                Privacy Policy
              </Link>{' '}
              for details).
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              7. Service Availability
            </h2>
            <p>
              We strive to keep ScholarHub available and reliable, but we do not guarantee
              uninterrupted or error-free service. The platform is provided on a "best effort" basis.
              We may perform maintenance, updates, or experience outages that temporarily affect
              availability.
            </p>
            <p className="mt-3">
              We are not liable for any loss of data or interruption caused by factors beyond our
              reasonable control.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              8. Free and Paid Plans
            </h2>
            <p>
              ScholarHub offers both free and paid subscription tiers. Features and limits associated
              with each tier are described on our pricing page and may change over time.
            </p>
            <p className="mt-3">
              We will provide at least 30 days' notice before making material changes to paid plan
              features or pricing. If you disagree with changes, you may cancel your subscription
              before they take effect.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              9. Termination
            </h2>
            <p>
              You may delete your account at any time. We may also suspend or terminate your account
              if you violate these Terms or if we discontinue the service.
            </p>
            <p className="mt-3">
              Upon termination, you may request an export of your research data by contacting us
              at{' '}
              <a href="mailto:support@scholarhub.space" className="text-indigo-600 dark:text-indigo-400 hover:underline">
                support@scholarhub.space
              </a>. We will make your data available for export for 30 days following account
              deletion.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              10. Limitation of Liability
            </h2>
            <p>
              To the maximum extent permitted by law, ScholarHub and its team shall not be liable
              for any indirect, incidental, special, consequential, or punitive damages arising from
              your use of or inability to use the service. This includes, but is not limited to,
              loss of data, loss of profits, or damages resulting from reliance on AI-generated
              content.
            </p>
            <p className="mt-3">
              Our total liability for any claim related to the service shall not exceed the amount
              you paid us in the 12 months preceding the claim, or $100, whichever is greater.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              11. Changes to Terms
            </h2>
            <p>
              We may update these Terms from time to time. If we make significant changes, we will
              notify you by email or through a prominent notice on the platform at least 14 days
              before the changes take effect. Your continued use of ScholarHub after changes are
              posted constitutes acceptance of the updated Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white mt-10 mb-4">
              12. Contact
            </h2>
            <p>
              If you have questions about these Terms, please contact us at{' '}
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

export default TermsOfService
