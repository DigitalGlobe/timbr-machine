import React from 'react';
import Sparkline from 'react-sparkline';
import Classnames from 'classnames';

const sparkVals = [];

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

    const statusClasses = Classnames(
      'machinestat-status', {
        'machinestat-status-running': status.running
      }
    );

    let processedPercent;
    let errPercent;
    if ( typeof status.processed !== 'undefined' ) {
      const totalQueued = status.processed + status.queue_size;
      processedPercent = Math.round(( status.processed / totalQueued )) * 100;

      const totalProcessed = status.errored + status.processed;
      errPercent = ( Math.round(( status.errored / totalProcessed ) * 10 ) / 10 ) * 100 || null;
    
      // grow the sparkline
      const diff = sparkVals.length ? status.processed - sparkVals[ sparkVals.length - 1 ] : 0;
      sparkVals.push( diff );

      if ( sparkVals.length > 30 ) { 
        sparkVals.shift();
      }
    } else {
      processedPercent = 0;
    }
 
    return ( 
      <div>
        <div className="machinestat">
          <h5>Timbr Machine Status</h5>
          <div className={ statusClasses }>{ running }</div>
          <div className="machinestat-row">
            <div className="machinestat-performance">
              <div className="machinestat-label">Average per minute</div>
              <div className="machinestat-sparkline">
                <Sparkline width={200} height={25} data={ sparkVals } strokeWidth={'2px'} strokeColor={'#98c000'} />
              </div>
              <div className="machinestat-movedown">
                <a href="#" className='btn btn-primary' onClick={ () => toggle( props ) }>{ action }</a>
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
                  <div className="machinestat-progress-processed" style={{ width: `${processedPercent}%` }}></div>
                  <div className="machinestat-progress-average" style={{ left: '68%' }}></div>
                  <div className="machinestat-progress-label-processed">{ status.processed }</div>
                  <div className="machinestat-progress-label-queued">{ status.queue_size }</div>
                </div>
              </div>
              <div className="machinestat-movedown">
                { errPercent ? `Errored: ${ status.errored } (${ errPercent }%)` : '' } <span className="machinestat-indent">Est. Completion: 100 seconds</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
}

export default DisplayStatus;
