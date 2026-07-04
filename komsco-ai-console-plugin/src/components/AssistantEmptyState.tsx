import * as React from 'react';

type AssistantEmptyStateProps = {
  iconSrc: string;
  text: string;
  title: string;
};

const AssistantEmptyState: React.FC<AssistantEmptyStateProps> = ({ iconSrc, text, title }) => (
  <div className="komsco-ai__empty">
    <div className="komsco-ai__empty-mark">
      <img alt="" className="komsco-ai__empty-logo" src={iconSrc} />
    </div>
    <div className="komsco-ai__empty-title">{title}</div>
    <div className="komsco-ai__empty-text">{text}</div>
  </div>
);

export default AssistantEmptyState;
