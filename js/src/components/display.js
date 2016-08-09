import React from 'react';
import { Sparklines, SparklinesLine, SparklinesSpots } from 'react-sparklines';
import Classnames from 'classnames';

const sparkVals = [];
const sparkAverages = [];
let processedVals;
let lastVal;

function toggle( props ) {
  const { status = {} } = props;
  props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: status.running ? 'stop' : 'start' } 
      }, props.cell.get_callbacks() );
}

function sum( vals ) {
  return vals.reduce( function( a, b ) {
    return a + b;
  });
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
    let average = 0;
    let errPercent;
    let timeLeft;

    let sparkMax = '';
    let sparkMin = '';
    let sparkAvg = '';

    if ( typeof status.processed !== 'undefined' ) {
      const totalProcessed = status.errored + status.processed;
      const totalQueued = totalProcessed + status.queue_size;
      
      processedPercent = ( totalProcessed / ( totalQueued + totalProcessed ) ) * 100;

      if ( !processedVals ) {
        processedVals = Array(10).fill( processedPercent );
      } else {
        processedVals.push( processedPercent );
        processedVals.shift();
      }

      average = sum( processedVals ) / processedVals.length;
      errPercent = ( Math.round(( status.errored / totalProcessed ) * 10 ) / 10 ) * 100 || null;
    
      // grow the sparkline
      if ( status.processed ) {
        if ( !lastVal ) {
          lastVal = status.processed;
        } else {
          sparkVals.push( status.processed - lastVal );
          lastVal = status.processed;

          if ( sparkVals.length > 1 ) {
            const windowSeconds = 10; 
            const windowVals = sparkVals.slice(Math.max(sparkVals.length - windowSeconds, 1))
            sparkAverages.push( sum( windowVals ) / windowVals.length );

            if ( sparkAverages.length > 30 ) {
              sparkAverages.shift();
            }

            sparkMax = Math.ceil( Math.max.apply(null, sparkAverages) );
            sparkMin = Math.round( Math.min.apply(null, sparkAverages) );
            sparkAvg = Math.round( sparkAverages[ sparkAverages.length - 1 ] * 10 ) / 10;
            timeLeft = Math.ceil( ( status.queue_size /  ( sum( sparkAverages ) / sparkAverages.length ) ) ); //seconds 
          }
        }
      }
    }


    return ( 
      <div>
        <div className="machinestat">
          <h5>Timbr Machine Status</h5>
          <div className={ statusClasses }>{ running }</div>
          <div className="machinestat-row">
            <div className="machinestat-performance">
              <div className="machinestat-label">Average per minute</div>
              <div className="machinestat-table">
                <div className="machinestat-cell machinestat-cell-tight">
                  <div className="machinestat-performance-high">{ sparkMax }</div>
                  <div className="machinestat-performance-low">{ sparkMin }</div>
                </div>
                <div className="machinestat-cell machinestat-cell-padded">
                  <div className="machinestat-sparkline">
                    <Sparklines data={sparkAverages} limit={30} width={175} height={25} margin={5}>
                      <SparklinesLine color="#98c000" style={{ strokeWidth: 1, stroke: "#98c000", fill: "none" }} />
                      <SparklinesSpots style={{ fill: "#98c000" }} />
                    </Sparklines>
                  </div>
                </div>
                <div className="machinestat-cell machinestat-cell-tight machinestat-cell-middle"><small>{ sparkAvg }</small></div>
              </div>

              <div className="machinestat-movedown">
                <a href="#" className='btn btn-primary' onClick={ () => toggle( props ) }>{ action }</a>
              </div>
            </div>
            <div className="machinestat-metastats">
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
                  <div className="machinestat-progress-average" style={{ left: `${average}%` }}></div>
                  <div className="machinestat-progress-label-processed">{ status.processed }</div>
                  <div className="machinestat-progress-label-queued">{ status.queue_size }</div>
                </div>
              </div>
              <div className="machinestat-movedown">
                { status.errored > 0 && errPercent ? <span>Errored: { status.errored } <span className="machinestat-meta">({ errPercent }%)</span></span> : ''}
                &nbsp;
                { status.processed && timeLeft ? <span className="machinestat-indent">Est. Completion: { timeLeft } seconds</span> : ''}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
}

export default DisplayStatus;
