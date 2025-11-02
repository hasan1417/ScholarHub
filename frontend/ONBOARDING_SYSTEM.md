# Onboarding System Documentation

## Overview

ScholarHub now has a comprehensive onboarding system to help new users understand and discover features. The system includes:

1. **Welcome Modal** - Introduces users to key features
2. **Feature Tour** - Interactive guided tour with highlighted elements
3. **Progress Tracking** - Persistent state using localStorage
4. **Progressive Disclosure** - Features revealed as users progress

---

## Components

### 1. OnboardingContext (`contexts/OnboardingContext.tsx`)

Central state management for onboarding progress.

**Tracked States:**
```typescript
{
  hasSeenWelcome: boolean           // User saw welcome modal
  hasCreatedFirstProject: boolean   // User created first project
  hasCreatedFirstPaper: boolean     // User created first paper
  hasUsedDiscovery: boolean         // User used discovery feature
  hasUsedCollaboration: boolean     // User used collaboration
  currentTourStep: number | null    // Active tour step
}
```

**Methods:**
- `markWelcomeSeen()` - Mark welcome as viewed
- `markFirstProjectCreated()` - Mark first project created
- `startTour(step)` - Start feature tour
- `nextTourStep()` - Advance to next step
- `endTour()` - End feature tour
- `resetOnboarding()` - Reset all onboarding state (for testing)

---

### 2. WelcomeModal (`components/onboarding/WelcomeModal.tsx`)

Beautiful multi-step modal introducing core features.

**Features:**
- 4-step welcome flow
- Feature highlights with icons
- Progress indicators
- Skip option

**Usage:**
```tsx
<WelcomeModal
  isOpen={showWelcome}
  onClose={() => setShowWelcome(false)}
  onGetStarted={() => {
    setShowWelcome(false)
    // Start feature tour or other action
  }}
/>
```

---

### 3. FeatureTour (`components/onboarding/FeatureTour.tsx`)

Interactive guided tour that highlights specific UI elements.

**Features:**
- Highlights target elements with animated rings
- Tooltips with navigation
- Smart positioning (top, bottom, left, right)
- Optional action buttons per step
- Dark overlay for focus

**Usage:**
```tsx
const tourSteps: TourStep[] = [
  {
    target: '[data-tour="create-project"]',  // CSS selector
    title: 'Create Your First Project',
    content: 'Start by creating a project...',
    placement: 'bottom',  // top | bottom | left | right
    action: {  // Optional
      label: 'Create a project',
      onClick: () => { /* action */ }
    }
  },
  // ... more steps
]

<FeatureTour
  steps={tourSteps}
  currentStep={currentStep}
  onNext={() => setCurrentStep(prev => prev + 1)}
  onPrevious={() => setCurrentStep(prev => prev - 1)}
  onSkip={() => setCurrentStep(null)}
  onComplete={() => {
    setCurrentStep(null)
    // Mark as complete
  }}
/>
```

---

## Integration Example (ProjectsHome)

```tsx
import { useOnboarding } from '../../contexts/OnboardingContext'
import WelcomeModal from '../../components/onboarding/WelcomeModal'
import FeatureTour, { TourStep } from '../../components/onboarding/FeatureTour'

const MyComponent = () => {
  const { state, markWelcomeSeen, startTour, endTour } = useOnboarding()
  const [showWelcome, setShowWelcome] = useState(false)

  // Show welcome on first visit
  useEffect(() => {
    if (!state.hasSeenWelcome) {
      setShowWelcome(true)
    }
  }, [state.hasSeenWelcome])

  // Define tour steps
  const tourSteps: TourStep[] = [
    {
      target: '[data-tour="button"]',
      title: 'Important Button',
      content: 'Click this to do something cool',
      placement: 'bottom',
    },
  ]

  // Add data-tour attributes to elements
  return (
    <div>
      <button data-tour="button">Click Me</button>

      <WelcomeModal
        isOpen={showWelcome}
        onClose={() => {
          setShowWelcome(false)
          markWelcomeSeen()
        }}
        onGetStarted={() => {
          setShowWelcome(false)
          markWelcomeSeen()
          startTour(0)  // Start tour after welcome
        }}
      />

      {state.currentTourStep !== null && (
        <FeatureTour
          steps={tourSteps}
          currentStep={state.currentTourStep}
          onNext={() => /* next step */}
          onPrevious={() => /* previous step */}
          onSkip={endTour}
          onComplete={endTour}
        />
      )}
    </div>
  )
}
```

---

## Adding Tour Steps to New Pages

1. **Import dependencies:**
```tsx
import { useOnboarding } from '../../contexts/OnboardingContext'
import FeatureTour, { TourStep } from '../../components/onboarding/FeatureTour'
```

2. **Add data-tour attributes** to elements you want to highlight:
```tsx
<button data-tour="my-feature">My Feature</button>
```

3. **Define tour steps:**
```tsx
const tourSteps: TourStep[] = [
  {
    target: '[data-tour="my-feature"]',
    title: 'My Feature',
    content: 'This feature does X, Y, Z...',
    placement: 'bottom',
  },
]
```

4. **Render FeatureTour** when appropriate:
```tsx
{onboardingState.currentTourStep !== null && (
  <FeatureTour
    steps={tourSteps}
    currentStep={onboardingState.currentTourStep}
    onNext={nextTourStep}
    onPrevious={/* ... */}
    onSkip={endTour}
    onComplete={endTour}
  />
)}
```

---

## Progressive Feature Introduction

You can trigger tours or highlights based on user progress:

```tsx
// Show discovery tour when user creates first project
useEffect(() => {
  if (onboardingState.hasCreatedFirstProject && !onboardingState.hasUsedDiscovery) {
    // Show tooltip or start discovery tour
  }
}, [onboardingState.hasCreatedFirstProject, onboardingState.hasUsedDiscovery])
```

---

## Testing

### Reset Onboarding State

To test the onboarding flow again:

```tsx
import { useOnboarding } from './contexts/OnboardingContext'

const { resetOnboarding } = useOnboarding()

// Call this to reset everything
resetOnboarding()
```

**Or manually in browser console:**
```javascript
localStorage.removeItem('scholarhub_onboarding')
location.reload()
```

---

## Customizing the Welcome Modal

Edit `components/onboarding/WelcomeModal.tsx`:

```tsx
const features = [
  {
    icon: FileText,
    title: 'Your Feature',
    description: 'Description here',
    color: 'indigo',  // Tailwind color
  },
  // Add more features
]
```

---

## Best Practices

### ✅ DO:
- Use data-tour attributes on stable elements that won't disappear
- Keep tour steps concise (3-5 steps max per tour)
- Provide skip options at every step
- Test onboarding flow regularly
- Update tours when UI changes significantly

### ❌ DON'T:
- Target dynamically rendered elements that might not exist
- Create overly long tours (breaks user attention)
- Force users through tours (always allow skipping)
- Forget to mark milestones (hasCreatedFirstProject, etc.)

---

## localStorage Structure

```javascript
{
  "scholarhub_onboarding": {
    "hasSeenWelcome": true,
    "hasCreatedFirstProject": true,
    "hasCreatedFirstPaper": false,
    "hasUsedDiscovery": false,
    "hasUsedCollaboration": false,
    "currentTourStep": null
  }
}
```

---

## Future Enhancements

Potential additions to the onboarding system:

1. **Contextual Help** - Show hints based on user actions
2. **Interactive Checklists** - Getting started checklist
3. **Video Tutorials** - Embedded tutorial videos
4. **Tooltips** - Persistent tooltip system for new features
5. **A/B Testing** - Test different onboarding flows
6. **Analytics** - Track which steps users complete/skip

---

## Troubleshooting

### Welcome modal not showing
- Check: `!onboardingState.hasSeenWelcome` condition
- Clear localStorage: `localStorage.removeItem('scholarhub_onboarding')`

### Tour not highlighting element
- Check: Element has correct `data-tour` attribute
- Check: Element exists in DOM when tour starts
- Check: CSS selector is correct in tourSteps

### Tour tooltip position wrong
- Adjust `placement` prop: 'top' | 'bottom' | 'left' | 'right'
- Element might be too close to viewport edge

---

## Summary

The onboarding system provides:
- ✅ Welcome modal for first-time users
- ✅ Interactive feature tours
- ✅ Persistent progress tracking
- ✅ Easy integration into new pages
- ✅ Customizable and extensible

**Result:** Better user experience, faster feature discovery, reduced learning curve.
