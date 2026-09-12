import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';

afterEach(() => cleanup());

describe('DashboardPage', () => {
  it('uses research-topic copy for the primary project action', () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(screen.getByRole('button', { name: /创建研究课题/ })).toBeInTheDocument();
    expect(screen.queryByText('新建项目')).not.toBeInTheDocument();
  });
});
