from .project_types import project_summary_bucket


def _value(result):
    return result.final_time or 0


def summarize_results(projects, results):
    project_by_id = {project.id: project for project in projects}
    total_time = 0
    total_score = 0
    time_count = 0
    score_count = 0

    for result in results:
        project = project_by_id.get(result.project_id)
        if not project or result.final_time is None:
            continue
        if project_summary_bucket(project) == 'score':
            total_score += _value(result)
            score_count += 1
        else:
            total_time += _value(result)
            time_count += 1

    all_score = bool(projects) and all(project_summary_bucket(project) == 'score'
                                       for project in projects)
    display_total = total_score if all_score else total_time
    return {
        'total_time': display_total,
        'time_total': total_time,
        'score_total': total_score,
        'time_count': time_count,
        'score_count': score_count,
        'all_score': all_score,
        'has_score': any(project_summary_bucket(project) == 'score'
                         for project in projects),
        'has_time': any(project_summary_bucket(project) == 'time'
                        for project in projects),
    }


def participant_result_summary(participant, projects, results):
    summary = summarize_results(projects, results)
    project_results = {}
    for project in projects:
        result = next((item for item in results
                       if item.project_id == project.id), None)
        project_results[project.id] = result.final_time if result else None

    return {
        'participant': participant,
        'results': results,
        'result_map': project_results,
        'project_results': project_results,
        'extra': participant.get_extra(),
        **summary,
    }


def ranking_sort_key(summary):
    if summary['all_score']:
        return (-summary['score_total'], summary['participant'].id)
    if summary['time_count']:
        return (summary['time_total'], -summary['score_total'],
                summary['participant'].id)
    return (float('inf'), -summary['score_total'], summary['participant'].id)
