import React from 'react';
import autobind from 'autobind-decorator';


function toggle( props ) {
  const { status = {} } = props;
  props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: status.running ? 'stop' : 'start' } 
      }, props.cell.get_callbacks() );
}

function DisplayStatus( props ) {
    const { status = {} } = props;
    const action = status.running ? 'Stop' : 'Start';
    const running = status.running ? 'Running' : 'Stopped';

    return ( 
      <div>
        <div className="machinestat">
          <h5>Timbr Machine Status</h5>
          <div className="machinestat-status machinestat-status-running">Running</div>
          <div className="machinestat-row">
            <div className="machinestat-performance">
              <div className="machinestat-label">Average per minute</div>
              <div className="machinestat-sparkline"></div>
              <div className="machinestat-movedown">
                <a href="#" className="btn btn-primary">Stop</a>
                <a href="#" className='btn-default' onClick={ () => toggle( props ) }>{ action }</a>
              </div>
            </div>
            <div className="machinestat-meta">
              <div className="machinestat-progress">
                <div className="machinestat-progress-key machinestat-label">
                  <ul>
                    <li className="key-queued">Queued</li>
                    <li className="key-processed">Processed</li>
                    <li className="key-average">Average</li>
                  </ul>
                </div>
                <div className="machinestat-progress-graph">
                  <div className="machinestat-progress-processed" style={{ width: '43%' }}></div>
                  <div className="machinestat-progress-average" style={{ left: '68%' }}></div>
                  <div className="machinestat-progress-label-queued">100.1k</div>
                  <div className="machinestat-progress-label-processed">100.1k</div>
                </div>
              </div>
              <div className="machinestat-movedown">
                Errored: 100 (0.5%) <span className="machinestat-indent">Est. Completion: 100 seconds</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
}

export default DisplayStatus;
